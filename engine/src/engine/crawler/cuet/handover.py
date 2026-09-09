"""Write the artifacts that make this corpus usable by someone who did not build it.

Three outputs, each for a different reader:

* `README.md`      — a person opening `corpus/cuet/` for the first time
* `pages.jsonl`    — `engine extract`, which expects a run directory
* `manifest.json`  — the same, plus counts and errors

The README is not documentation for its own sake. This corpus has three
properties that will silently produce wrong results if the next person does not
know about them, and all three are consequences of decisions taken here rather
than facts about CUET. They are written down where the data is, because a spec
in a repo root is not where somebody looks when a number seems off.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from engine.contracts.documents import CrawledPage

from . import config

log = logging.getLogger(__name__)


def write_pages_jsonl(rows: list[dict], out: Path) -> int:
    """One CrawledPage per document, in the engine's run-directory shape.

    `engine extract --run <dir>` is the whole interface between capture and
    extraction (engine/src/engine/knowledge/README.md §3), and `content_path`
    must point at a file that actually exists inside the run directory.

    Rows arrive from the shards, already reduced to the CrawledPage fields by
    `content._crawled_page_row`, so this function does no re-derivation. It is
    called by `merge.py` and nowhere else.
    """
    written = 0
    with (out / "pages.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            page = CrawledPage(
                page_id=row["page_id"],
                url=row["url"],
                canonical_url=row["canonical_url"],
                status=row.get("status", 200),
                content_type="text/html",
                content_path=row["content_path"],
                fetched_at=row["fetched_at"],
                depth=0,
                links=[],
                document_links=row.get("document_links", []),
                parent_url="",
                meta={"source": row.get("source", "api"),
                      "section": row.get("section", ""),
                      "section_path": row.get("section_path", [])},
            )
            problems = page.validate()
            if problems:
                log.warning("CrawledPage %s invalid: %s", page.page_id, problems)
                continue
            handle.write(json.dumps(page.__dict__, ensure_ascii=False, default=str) + "\n")
            written += 1
    return written


def write_manifest(out: Path, *, run_id: str, started: str, finished: str,
                   documents: int, pages: int, files: dict, errors: list,
                   portions: list[str] | None = None) -> None:
    """Counts, errors and provenance for the merged corpus.

    `portions` records which slices of the site this corpus actually contains.
    A corpus merged from three shards out of four is not broken, but it IS
    incomplete, and the manifest is the only place that difference is visible
    once the terminal output is gone.
    """
    manifest = {
        "run_id": run_id,
        "site": "cuet",
        "portions": portions or [],
        "seeds": [config.SITE, config.API],
        "started_at": started,
        "finished_at": finished,
        "pages_fetched": documents,
        "pages_written": pages,
        "pages_skipped": 0,
        "errors": errors,
        "config": {"delay": config.DELAY, "user_agent": config.USER_AGENT,
                   "obey_robots": config.OBEY_ROBOTS},
        "assets_saved": {"document": files.get("downloaded", 0)},
        "documents_parsed": 0,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


README = """# CUET capture — what this is and how to use it

Produced by the CUET scraper at `engine/src/engine/crawler/cuet/`.
Specification: `CUET_SCRAPER_SPEC.md` (Part 1) and
`CUET_SCRAPER_SPEC_PART2.md`. Both are gitignored and live on Google Drive;
the repo README has the link.

## Read this before you embed anything

**1. Pass `--min-text-chars 50`.** `engine extract` drops documents below 200
characters as navigation. A number of documents here are legitimately shorter
than that, and at the default they vanish with no error and no count. If
`documents.jsonl` comes out at roughly half the size of this corpus, this is why.

**2. Most of this content came from a JSON API, not from rendered HTML.** Every
document records which, in `source`: `"api"` or `"browser"`. Practically, `api`
documents are already clean — no navigation, no cookie banner, no footer — so
there is nothing for a selector to strip. Do not go looking for chrome that
is not there. The `browser` documents are ordinary captured HTML and behave the
way you expect.

**3. `url` and `doc_key` are not always the same.** `url` is the page a citation
should show a reader, and it always resolves on cuet.ac.bd. `doc_key` is what
`doc_id` is derived from. They differ only where one real page yields several
documents — see "Notices" below. Cite `url`; join on `page_id`.

**4. `documents.jsonl` is generated, not committed.** Run `--stage merge` after
pulling. See "The generated files" below.

## Which folder is which part of the website

Every content folder maps to somewhere a visitor can actually go. If you are
checking whether a document is right, open the URL in the last column.

{folder_table}

Three folders hold no page content:

| Folder | What it is |
|---|---|
| `_shards/` | One file per portion. **The committed source of truth.** |
| `_meta/` | Provenance: `api_dump.json`, the audit, the URL plan, errors |
| `_files/` | Every downloaded PDF, flat, plus `index.json` |

`_unsorted/` is not a mistake here. Those 15 documents are the notice types
Part 1 deliberately leaves out of scope; they all cite `/notices/all-notice`,
which is the real page the site lists them on. A document arriving in
`_unsorted/` from anywhere else IS a mistake and means the section map in
`config.SECTIONS` has a gap.

Files are flat in `_files/` on purpose: the same PDF is linked from many pages,
so a per-section copy would leave no canonical one. `_files/index.json` carries
the title, date, category, department and `linked_from` list for each.

## The generated files, and why they are not committed

```
corpus/cuet/
├── _shards/          COMMITTED. One JSON per portion — the source of truth.
├── <section folders> COMMITTED. The .html/.md/.json triple per document.
├── _files/           On Google Drive, too large for git.
├── _meta/            api_dump.json on Drive; the rest generated.
│
├── documents.jsonl   GENERATED by --stage merge
├── pages.jsonl       GENERATED — the `engine extract --run` interface
├── manifest.json     GENERATED — counts, errors, which portions are present
└── README.md         GENERATED — this file
```

If `documents.jsonl` is missing, nothing is wrong. Run:

```bash
python -m engine.crawler.cuet --stage merge
```

It reads `_shards/`, needs no network, and takes about a second. Those files are
generated rather than committed because four people each rebuild them in full,
and a committed file that four people rewrite is a merge conflict on every pull
request in a format nobody can resolve by hand. The shards do not have that
problem: one file per portion, one owner each.

The merge is deterministic — documents sort by `doc_id`, files and pages by URL
— so two people merging the same shards get byte-identical output. That is what
makes "just regenerate it" a real answer.

## Two shapes of document, and why

Most documents are one page of the site: a department, a news item, a CMS page.
Those are unremarkable.

**Notices and curricula are index documents, not one document per item.** This
was a deliberate choice and it is the one thing here most likely to surprise you.

A notice record is a title, a date, a type and a link to a PDF — it has no prose.
Emitting one document per notice would have produced 265 texts under "Offices
Orders/NOC" that differ only in a title and a date, each repeating the same
boilerplate. Embedded, those become hundreds of near-identical vectors that
crowd out real content in every retrieval, and most would then be dropped by the
200-character threshold anyway.

So each notice type becomes a small number of index documents holding a table of
its notices, split at 60 rows. Chunking splits those into runs of titles, each
chunk genuinely distinct. The PDFs themselves are downloaded, and their
searchable metadata lives in `_files/index.json`.

If you would rather have one document per notice, everything needed is in
`_meta/api_dump.json` under `/notices` — no re-crawl required. That is the point
of keeping the raw payloads.

## What is NOT here

- **No images, anywhere.** Not an oversight: nothing downstream can embed a PNG.
  Alt text and figure captions ARE kept, since they are prose. `_files/` should
  contain zero image files; if it ever does, that is a bug worth reporting.
- **Nothing behind a login.** No authenticated request was made.
- Sections deliberately out of scope for Part 1 — Research, most Notice types,
  Administration, APA — are listed in `CUET_SCRAPER_SPEC_PART2.md`. Their raw
  API payloads are already in `_meta/api_dump.json`.

## Provenance

`_meta/api_dump.json` holds every API response verbatim, saved before any
parsing. If an extraction decision here turns out to be wrong, it can be redone
offline against those bytes rather than by re-crawling a university's server.

`_meta/endpoints.json` is the output of `--stage audit`, which re-derives the
site's API endpoint list from its live JavaScript bundles. If it reports
anything under `undocumented`, this corpus was built against a stale inventory
and may be missing a whole content type. Run it before trusting a re-run.
"""



# Where each content folder is on the live site. The counts are NOT here: they
# are read off the corpus when the README is written, because a hand-typed count
# is wrong the first time anybody captures anything and nobody notices for weeks.
# This table was carrying "academic/information | 2" long after it held 5, and
# had no row at all for the 374 faculty profiles.
#
# A folder missing from this map still appears in the README, marked so that the
# gap is visible rather than silently dropped.
FOLDER_MAP: dict[str, tuple[str, str]] = {
    "_cms": ("About menu (`/about/cuet`, `/about/history`, "
             "`/about/vision-and-mission`, `/about/campus-life`), prospective "
             "students (`/academic-information/undergraduate-studies`, "
             "`/academic-information/graduate-studies`), research "
             "(`/research/research-highlights`, `/research/research-area`)",
             "general"),
    "home": ("The site homepage, `/`", "browser"),
    "home/organizations": ("Student Organizations, `/student/organization/<slug>`",
                           "general"),
    "academic/departments": ("Academic -> Departments, `/department/<slug>`, plus "
                             "`/department/<slug>/academic/undergraduate` and "
                             "`/academic/postgraduate`", "academic"),
    "academic/faculty": ("Academic -> Faculties, `/faculty/<slug>`", "academic"),
    "academic/institutes": ("Academic -> Institutes, `/institutes/<slug>`", "academic"),
    "academic/centers": ("Academic -> Centers, `/centers/<slug>`", "academic"),
    "academic/information": ("`/academic-information` and its pages: academic "
                             "calendars, undergraduate and graduate studies, "
                             "international students", "academic"),
    "academic/profiles": ("Every faculty member, `/profile/faculty-member/<slug>`",
                          "academic"),
    "academic/notices": ("Notices -> Academic Calender, `/notices/academic-calender`",
                         "notices"),
    "admission": ("Admission menu: `/admission`, `/admission/msc`, `/fsc`, "
                  "`/student/undergraduate-student`, `/student/postgraduate-student`",
                  "notices"),
    "admission/notices": ("Notices -> Scholarship & Financial Aids, "
                          "`/notices/scholarship-financial-aids`", "notices"),
    "top-bar/notices": ("The top-bar NOC link, `/notices/noc`", "notices"),
    "news-events/news": ("News & Events -> News, `/news/<id>`", "news-events"),
    "news-events/event-details": ("News & Events -> Events, `/event-details/<id>`",
                                  "news-events"),
    "news-events/listing": ("The listing pages themselves, `/news-events`, "
                            "`/events`, `/student/events`", "news-events"),
    "alumni/pages": ("alumni.cuet.ac.bd CMS pages, `/` and `/about`", "alumni"),
    "alumni/news": ("alumni.cuet.ac.bd news, `/news/<id>`", "alumni"),
    "alumni/notices": ("alumni.cuet.ac.bd notices, `/notices`", "alumni"),
    "alumni/directory": ("alumni.cuet.ac.bd directory, `/alumnis/<id>`", "alumni"),
    "alumni/responsibilities": ("Alumni responsibilities, shown on the alumni "
                                "homepage", "alumni"),
    "_unsorted/notices": ("Notice types out of scope for Part 1, all listed at "
                          "`/notices/all-notice`", "notices"),
}


def _folder_table(out: Path) -> str:
    """The folder-to-website map, counted from what is actually on disk."""
    counts: dict[str, int] = {}
    skip = {"_shards", "_meta", "_files"}
    for path in out.rglob("*.json"):
        parts = path.relative_to(out).parts
        if skip & set(parts) or len(parts) < 2:
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(meta, dict) or not meta.get("page_id"):
            continue
        counts["/".join(parts[:-1])] = counts.get("/".join(parts[:-1]), 0) + 1

    rows = ["| Folder | Documents | Where it is on the live site | Portion |",
            "|---|---|---|---|"]
    for folder in sorted(counts):
        where, portion = FOLDER_MAP.get(
            folder, ("**not in FOLDER_MAP** - add it to handover.py", "?"))
        rows.append(f"| `{folder}/` | {counts[folder]} | {where} | {portion} |")
    rows.append(f"| **total** | **{sum(counts.values())}** | | |")
    return "\n".join(rows)


def write_readme(out: Path) -> None:
    (out / "README.md").write_text(
        README.format(folder_table=_folder_table(out)), encoding="utf-8")


def write_all(out: Path, rows: list[dict], *, run_id: str, started: str,
              files: dict | None = None, errors: list | None = None) -> int:
    pages = write_pages_jsonl(rows, out)
    write_readme(out)
    write_manifest(
        out, run_id=run_id, started=started,
        finished=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        documents=len(rows), pages=pages,
        files=files or {}, errors=errors or [],
    )
    return pages
