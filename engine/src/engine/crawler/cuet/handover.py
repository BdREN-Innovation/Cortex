"""Write the artifacts that make this corpus usable by someone who did not build it.

Three outputs, each for a different reader:

* `README.md`      — a person opening `cuet_data/` for the first time
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
                content_path=row["html_path"],
                fetched_at=row["fetched_at"],
                depth=0,
                links=[],
                document_links=[f["url"] for f in row.get("files", [])],
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
                   documents: int, pages: int, files: dict, errors: list) -> None:
    manifest = {
        "run_id": run_id,
        "site": "cuet",
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

Produced by `cuet_scraper`. Specification: `CUET_SCRAPER_SPEC.md` (Part 1) and
`CUET_SCRAPER_SPEC_PART2.md` in the repository root.

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

## Layout

```
cuet_data/
├── documents.jsonl   CleanDocument rows for the API-derived content
├── pages.jsonl       CrawledPage rows — the `engine extract --run` interface
├── manifest.json     counts, errors, config
├── _meta/            api_dump.json (raw responses), urls.txt, found_*.txt,
│                     endpoints.json (audit), errors.json, run.json
├── _cms/             the 8 page bodies from /general-settings
├── academic/         departments, institutes, centers, faculties, curricula
├── home/             homepage body, student organisations
├── top-bar/          NOC notices
├── news-events/      news and events
└── _files/           every downloaded PDF, flat, plus index.json
```

Files are flat in `_files/` on purpose: the same PDF is linked from many pages,
so a per-section copy would leave no canonical one. `_files/index.json` carries
the title, date, category, department and `linked_from` list for each.

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


def write_readme(out: Path) -> None:
    (out / "README.md").write_text(README, encoding="utf-8")


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
