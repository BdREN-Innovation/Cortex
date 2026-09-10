# Cortex Data Inventory & Guide

Where the scraped data lives, how it is structured, and how Team B (Knowledge,
Extraction, Embeddings) and Team C (Evaluation) should consume it.

This is the single reference for the CUET capture. Two earlier documents
(`CUET_SCRAPER_README_MERGED.md`, `SCRAPE_INVENTORY.md`) said the same things
with older numbers and have been removed rather than left to contradict this one.
The specifications `CUET_SCRAPER_SPEC.md` and `CUET_SCRAPER_SPEC_PART2.md` stay
out of the repo and live on Google Drive.

---

## 1. Who built what

The CUET crawler is split into **portions**, one slice of the website each, so
that several people can work in parallel without editing the same files. Each
portion owns its own builder module and writes its own shard.

| Portion | Owner | Part of the site |
|---|---|---|
| `academic` | **Samonwita Sarker** | Departments, faculties, institutes, centres, academic information, all faculty profiles |
| `news-events` | **Samonwita Sarker** | News items, events, and the listing pages |
| `alumni` | **Samonwita Sarker** | The whole of `alumni.cuet.ac.bd` |
| `notices` | unassigned | All notice types. The NOC notices in it are Samonwita's; the other types are not |
| `general` | unassigned | About menu, research pages, student organisations |

`notices` and `general` are deliberately unowned. Neither maps to one person, and
naming a single owner would claim work that is not theirs.

### Samonwita Sarker's part

Six areas of the website, **649 of the 687 documents** in the corpus.

| Area | Documents | Where it is on the site |
|---|---|---|
| Homepage | 1 | `/` |
| Academic | 458 | `/departments`, `/department/<slug>`, `/faculty`, `/institutes`, `/centers`, `/academic-information`, `/profile/faculty-member/<slug>` |
| News & Events | 163 | `/news/<id>`, `/event-details/<id>`, `/news-events`, `/events`, `/student/events` |
| Alumni | 15 | the whole `alumni.cuet.ac.bd` host |
| Admission | 6 | `/admission`, `/admission/msc`, `/fsc`, `/student/undergraduate-student`, `/student/postgraduate-student`, `/notices/scholarship-financial-aids` |
| NOC notices | 6 | `/notices/noc`, the top-bar NOC link |

The remaining 38 documents are the About pages, the research pages, the student
organisations and the combined notice listing, which belong to other portions.

---

## 2. High-level data map

| Site | Location | Type | Format |
|---|---|---|---|
| **CUET** | `engine/corpus/cuet/` | Curated reference corpus | `.md`, `.json`, `.html` triples, `documents.jsonl`, `pages.jsonl` |
| **BDREN** | `engine/data/sites/bdren/bdren-20260909T110121Z/` | Crawler runtime run | 40 pages, 33 PDFs | `raw/*.html`, `docs/*.pdf`, `pages.jsonl` |
| **BUBT** | `engine/data/sites/bubt/bubt-20260908T220949Z/` | Crawler runtime run | `raw/*.html`, `docs/*.pdf`, `pages.jsonl` |
| **Green University** | `engine/data/sites/green/green-20260908T220124Z/` | Crawler runtime run | `raw/*.html`, `pages.jsonl` |

The CUET corpus is different in kind from the other three. It was built
API-first: **634 of its 687 documents came from CUET's public JSON API**, and
only 53 from a headless browser. API documents arrive as clean prose with no
navigation, banner or footer, so there is nothing for a boilerplate stripper to
remove.

---

## 3. The CUET corpus

### 3.1 Folder map, with the website location of each

Every content folder corresponds to somewhere a visitor can go. To check whether
a document is right, open the URL.

| Folder | Docs | Where it is on the live site |
|---|---|---|
| `academic/profiles/` | 382 | Every faculty member, `/profile/faculty-member/<slug>`. Covers all three employee statuses: 374 current, 2 on leave, 6 retired |
| `news-events/news/` | 157 | News & Events → News, `/news/<id>` |
| `academic/departments/` | 55 | `/department/<slug>` for 18 departments, plus each one's `/academic/undergraduate` and `/academic/postgraduate` |
| `home/organizations/` | 15 | Student Organizations, `/student/organization/<slug>` |
| `_unsorted/notices/` | 15 | Notice types out of scope for Part 1, all listed at `/notices/all-notice` |
| `_cms/` | 8 | About menu, prospective-student pages, research pages |
| `top-bar/notices/` | 6 | The top-bar NOC link, `/notices/noc` |
| `academic/faculty/` | 6 | Academic → Faculties, `/faculty` and `/faculty/<slug>` |
| `academic/information/` | 5 | `/academic-information` and its pages |
| `academic/institutes/` | 5 | Academic → Institutes, `/institutes/<slug>` |
| `admission/` | 5 | The Admission menu |
| `academic/centers/` | 4 | Academic → Centers, `/centers/<slug>` |
| `alumni/news/` | 4 | `alumni.cuet.ac.bd/news/<id>` |
| `alumni/pages/` | 4 | `alumni.cuet.ac.bd/` and `/about` |
| `alumni/responsibilities/` | 4 | Alumni responsibilities, on the alumni homepage |
| `news-events/event-details/` | 3 | News & Events → Events, `/event-details/<id>` |
| `news-events/listing/` | 3 | `/news-events`, `/events`, `/student/events` |
| `alumni/directory/` | 2 | `alumni.cuet.ac.bd/alumnis/<id>` |
| `academic/notices/` | 1 | Notices → Academic Calender |
| `admission/notices/` | 1 | Notices → Scholarship & Financial Aids |
| `alumni/notices/` | 1 | `alumni.cuet.ac.bd/notices` |
| `home/` | 1 | The site homepage, `/` |
| **Total** | **687** | |

This table is regenerated from disk by `--stage merge` into
`engine/corpus/cuet/README.md`. It is reproduced here for convenience; that file
is the one that cannot go stale.

`_unsorted/` is not a mistake. Those 15 documents are notice types Part 1 leaves
out of scope, and they cite `/notices/all-notice`, the page the site really lists
them on. A document arriving in `_unsorted/` from anywhere else **is** a mistake
and means `config.SECTIONS` has a gap.

### 3.2 Three folders that hold no page content

| Folder | What it is |
|---|---|
| `_shards/` | One JSON file per portion. **The committed source of truth.** |
| `_meta/` | Provenance: the raw API dump, the URL plan, errors, known gaps |
| `_files/` | Every downloaded PDF, flat, plus `index.json` |

Files are flat in `_files/` because the same PDF is linked from many pages, so a
per-section copy would leave no canonical one. `_files/index.json` carries the
title, date, category, department and `linked_from` list for each.

### 3.3 Every document is three files

```
<slug>__<first 8 of doc_id>.html   the bytes as captured
<slug>__<first 8 of doc_id>.md     converted to markdown
<slug>__<first 8 of doc_id>.json   metadata sidecar
```

The `.json` is written **last**, so it doubles as the completion marker: HTML
present with no JSON means the write was interrupted and the document is retried.

Useful sidecar fields:

| Field | Meaning |
|---|---|
| `url` / `canonical_url` | The page a citation should show a reader. Always resolves. |
| `doc_key` | What `doc_id` is derived from. Differs from `url` where one page yields several documents. |
| `page_id` | Stable id. Join on this. |
| `source` | `"api"` or `"browser"` |
| `fetched_at` | When the bytes came off CUET's servers, not when the file was rebuilt |
| `content_state` | `"published"`, or `"placeholder"` where the page exists but CUET has not published its content |
| `private_fields_dropped` | Present on people records. Names the fields deliberately not stored. |

### 3.4 Provenance: where each document and each PDF came from

Two generated files answer "where is this from?" without reading the crawler.

**`_meta/provenance.jsonl`** has one row per document and one per file. A
document row names the endpoint that produced it, not just whether it was API or
browser, plus the portion, its owner, the live URL, and where the raw bytes are:

```json
{"kind": "document", "doc_id": "...", "title": "Civil Engineering",
 "live_url": "https://cuet.ac.bd/department/CE",
 "origin": "API /administrative-departments/{slug}", "source": "api",
 "section": "academic", "portion": "academic", "owner": "Samonwita Sarker",
 "fetched_at": "...", "content_path": "academic/departments/CE__....html",
 "raw_payload": "_meta/api_dump.json"}
```

`raw_payload` points at `_meta/api_dump.json` for API documents and at the saved
render for browser ones, so any disagreement is settled against bytes rather than
by re-crawling.

The 687 documents come from 14 distinct origins:

| Documents | Origin |
|---|---|
| 382 | API `/app-admins/{slug}` |
| 157 | API `/news` |
| 53 | browser render (crawl4ai + Chromium) |
| 30 | API `/administrative-departments/{slug}` |
| 22 | API `/notices` + `/notice-types` |
| 15 | API `/student-organizations` |
| 8 | API `/general-settings` |
| 4 each | alumni `/alumni-settings`, `/alumni-home-data` (news), `/alumni-responsibilities` |
| 3 | API `/events` |
| 2 each | alumni `/alumnis`, API `/academic-curriculums` |
| 1 | alumni `/alumni-home-data` (notices) |

**`_files/index.json`** is the same mapping from the PDF side, and it is where to
look while holding a file. Each of the 1,001 entries carries the download fields
plus a resolved `sources` list:

```json
{"url": "https://app.cuet.ac.bd/storage/Downloads/....pdf",
 "local": "_files/de1bedf5__....pdf", "bytes": 2912170,
 "title": "Term-wise Course Distribution and Related Information",
 "document_type": "page", "downloaded": true,
 "linked_from": ["https://cuet.ac.bd/academic-information", "..."],
 "sources": [{"doc_id": "...", "title": "Postgraduate curricula",
              "live_url": "https://cuet.ac.bd/academic-information",
              "section": "academic", "portion": "academic",
              "owner": "Samonwita Sarker",
              "origin": "API /academic-curriculums"}],
 "unresolved_links": []}
```

Three things about it are deliberate.

- **A PDF may have several sources, and all are kept.** 39 files are linked from
  more than one document. Keeping one would invent a relationship the site does
  not have.
- **`linked_from` is untouched and `sources` is additive**, so anything already
  reading the URL list keeps working.
- **A link that resolves to no document is named in `unresolved_links`** rather
  than silently producing an empty `sources`, which would read as a bug. All
  1,001 currently resolve.

Both files are regenerated by `--stage merge`, offline. The index preserves
`local`, `bytes` and `content_type` across rebuilds, so a metadata change never
means re-downloading the PDFs.

### 3.4 Files generated by merge, not committed

```
documents.jsonl   CleanDocument rows
pages.jsonl       the engine extract --run interface
manifest.json     counts, errors, which portions are present
README.md         the folder table above, regenerated
```

If these are missing, nothing is wrong:

```bash
cd engine
uv run python -m engine.crawler.cuet --stage merge
```

It reads `_shards/`, needs no network, and takes about a second. They are
generated rather than committed because several people each rebuild them in
full, and a committed file that everyone rewrites conflicts on every pull
request. The merge is deterministic, so two people merging the same shards get
byte-identical output.

---

## 4. The crawler code

`engine/src/engine/crawler/cuet/`

### 4.1 Pipeline stages

Run with `python -m engine.crawler.cuet --stage <name>`.

| Stage | File | What it does |
|---|---|---|
| `discover` | `discover.py` | Fetches all 17 API endpoints plus 30 entity details, 382 faculty profiles and 7 alumni endpoints. Saves every response verbatim to `_meta/api_dump.json` before parsing. Builds the residual URL plan. |
| `content` | `content.py` | Turns the saved payloads into documents. Runs one or more portions; each writes its own shard. |
| `merge` | `merge.py` | Assembles the shards into the corpus files. No network. |
| `plan` | `discover.py` | Prints the residual URL plan. |
| `capture` | `capture.py` | Renders the pages the API cannot produce, in headless Chromium. Resumable. |
| `reharvest` | `capture.py` | Re-extracts links from saved HTML. **No network.** Changing what counts as a link costs a second, not a re-crawl. |
| `files` | `files.py` | Downloads the in-scope PDFs. |
| `audit` | `audit.py` | Re-derives the API endpoint list from the site's live JavaScript bundles and reports anything undocumented. |
| `verify` | `verify.py` | Runs the specification's definition of done, 26 checks. Exits non-zero on failure. |

`--portion <name>` restricts a content run to one slice. `--list-portions` shows
them.

### 4.2 What each module is for

| File | Lines | Purpose |
|---|---|---|
| `config.py` | 753 | Every tunable value, and the evidence for the non-obvious ones. Read this first. |
| `verify.py` | 462 | The definition of done, as executable checks. |
| `capture.py` | 401 | Browser rendering, failed-render and 404 detection, offline re-harvest. |
| `content.py` | 359 | Writes the document triple and the per-portion shard. |
| `handover.py` | 326 | Writes `pages.jsonl`, `manifest.json` and the corpus README. |
| `paths.py` | 275 | Canonicalisation, stable ids, section and group routing. |
| `api.py` | 276 | One polite HTTP client: per-host delay, robots, retries. |
| `discover.py` | 259 | Stage 1 and the URL plan. |
| `merge.py` | 220 | Deterministic shard assembly, plus `known_gaps.json`. |
| `markdown.py` | 202 | HTML to markdown on the standard library's parser. |
| `audit.py` | 112 | Endpoint inventory from live bundles. |
| `files.py` | 114 | PDF downloads. |
| `__main__.py` | 228 | CLI and run bookkeeping. |

### 4.3 The builders

`builders/` holds one module per portion, so owners never edit the same file.

| File | Lines | Produces |
|---|---|---|
| `__init__.py` | 164 | The portion registry. The one shared file, deliberately tiny. |
| `academic.py` | 306 | Departments, faculties, institutes, centres, curricula, and all 382 faculty profiles. |
| `alumni.py` | 267 | The alumni site's CMS pages, news, notices, responsibilities and directory. |
| `base.py` | 222 | The `Document` model, link harvesting, shared helpers. Nothing portion-specific. |
| `notices.py` | 133 | Every notice type, as index documents. |
| `news.py` | 86 | News items and events. |
| `general.py` | 66 | CMS page bodies and student organisations. |

### 4.4 Tests

`engine/tests/crawler/cuet/`, **201 tests**, no network required.

| File | Tests | Covers |
|---|---|---|
| `test_paths.py` | 45 | Canonicalisation, ids, host and section rules |
| `test_content.py` | 26 | Document building over synthetic payloads |
| `test_coverage.py` | 24 | Placeholder pages, dismissals, gap attribution |
| `test_alumni.py` | 15 | The alumni portion and its privacy rule |
| `test_portions.py` | 15 | The multi-person split |
| `test_faculty.py` | 17 | Faculty profiles, their privacy rule, and every employee status |
| `test_capture.py` | 12 | Failed-render and 404 detection |
| `test_shards.py` | 12 | Shard building and the resume case |
| `test_harvest.py` | 10 | Link harvesting and HTML entity decoding |
| `test_known_gaps.py` | 6 | Unreachable hosts recorded rather than hidden |
| `test_handover_map.py` | 5 | The folder map cannot fall behind the corpus |

```bash
cd engine && uv run pytest tests -q
```

---

## 5. What Team B needs to know

**1. Pass `--min-text-chars 50`.** `engine extract` drops documents under 200
characters as navigation. Some documents here are legitimately shorter, and at
the default they vanish with no error and no count.

**2. Do not strip boilerplate from `source == "api"` documents.** They have no
navigation, cookie banner or footer to remove. Writing selectors for chrome that
is not there will cut real content. The 53 `browser` documents are ordinary
captured HTML and behave as expected.

**3. `url` and `doc_key` are not always the same.** Cite `url`; join on
`page_id`. They differ where one real page yields several documents, which is how
notices and curricula work.

**4. Notices and curricula are index documents, not one document per item.** A
notice record is a title, a date, a type and a PDF link, with no prose. One
document per notice would produce hundreds of near-identical texts that crowd out
real content in every retrieval, and most would fall under the length threshold
anyway. Each notice type becomes a few index documents holding a table, split at
60 rows. The PDFs are downloaded and their metadata is in `_files/index.json`. If
you want one document per notice, everything needed is in `_meta/api_dump.json`
under `/notices`, with no re-crawl.

**5. Check `content_state`.** 20 of the per-department academic pages carry
`"placeholder"`: the page and route are real, but CUET has not published the
curriculum. They are kept rather than dropped, because thin-page filtering
belongs downstream where it can be reconsidered. Filter them if you want.

**6. 122 documents contain Bangla.** Verified as correctly decoded, no mojibake.
**7. Faculty documents cover three employee statuses.** 374 current staff, 2 on
leave and 6 retired, 382 in all. The endpoint defaults to current staff without
saying so, which is how the other 8 were missed on the first pass. Each document
records `employee_status`, so filtering to current staff is your choice to make.


---

## 6. Decisions worth knowing before you trust the data

**People records omit fields the website does not display.** The faculty endpoint
returns national ID, date of birth, blood group, parents' names, permanent
address, religion and personal email. The public profile page shows none of them.
Every one is dropped before a document is written, and the identity fields are
dropped even though the API currently returns them as null, so that a backend
change cannot quietly push them into the corpus. Work email, office phone and
room number are kept, because those are on the page. The same rule applies to
the alumni directory. Each affected document lists what was removed in
`private_fields_dropped`.

**Nothing behind a login was fetched.** No authenticated request was made.

**No images anywhere.** Not an oversight: nothing downstream can embed a PNG. Alt
text and captions are kept, since they are prose. `_files/` should contain zero
image files.

**Politeness.** 1.5 seconds per host, a real contact address in the User-Agent,
and 404 and 403 are never retried. Neither `cuet.ac.bd` nor `alumni.cuet.ac.bd`
serves a robots.txt; both return 404, and the alumni pages carry no robots meta
tag either.

**Known gaps are written down, not hidden.** `_meta/known_gaps.json` lists every
planned URL that is not in the corpus, with the reason and whether re-running
could fix it. Today it holds two: `admissioncuet.ac.bd` and its about page, which
have no DNS record at all. They are left in the plan on purpose, because the
Admission menu really does link to a host that no longer exists.

---

## 7. Multi-site crawl runs (`engine/data/sites/`)

The standard runtime artifact format produced by the Cortex CLI.

```
engine/data/sites/<site>/<site>-<timestamp>/
├── manifest.json    run summary: duration, status, URLs crawled, file counts
├── pages.jsonl      Team A deliverable: URLs, hashes, content types, status
├── raw/             raw HTML snapshots named by xxhash
└── docs/            downloaded non-HTML assets
```

### Sites Captured
1. **BDREN (`engine/data/sites/bdren/bdren-20260909T110121Z/`)**:
   - `pages.jsonl`: 40 captured pages.
   - `docs/`: 33 downloaded document PDFs.
   - `raw/`: 40 raw HTML files.
2. **BUBT (`engine/data/sites/bubt/bubt-20260908T220949Z/`)**:
   - `pages.jsonl`: 100 captured pages.
   - `docs/`: Academic routines and program syllabus PDFs (`BBA-routine.pdf`, `msc-in-cse.pdf`, etc.).
   - `raw/`: 100 raw HTML files.
3. **Green University (`engine/data/sites/green/green-20260908T220124Z/`)**:
   - `pages.jsonl`: 5 captured pages.
   - `raw/`: 5 raw HTML files.

```bash
cd engine
uv run engine extract --run data/sites/bubt/bubt-20260908T220949Z
uv run engine extract --run data/sites/bdren/bdren-20260909T110121Z
uv run engine extract --run data/sites/green/green-20260908T220124Z
```

---

## 8. Heavy assets and the Google Drive backup

Large binaries and the specifications are gitignored to keep the repository
light. They live on Drive:

> **[Cortex — Gitignored Data (Google Drive)](https://drive.google.com/drive/folders/1FhWXKBVmA1X_y4S0mvD5qgIQgtiZ7xVA)**

| Drive folder | Local destination | Contents |
|---|---|---|
| `01_scraped_documents/*.pdf` | `engine/corpus/cuet/_files/` | CUET notice and circular PDFs. **PDFs only, see below** |
| `02_api_metadata/*` | `engine/corpus/cuet/_meta/` | `api_dump.json`, every API response verbatim |
| `03_scraper_specs/*` | repo root | `CUET_SCRAPER_SPEC.md`, `CUET_SCRAPER_SPEC_PART2.md` |

`api_dump.json` holds every API response exactly as returned, saved before any
parsing. If an extraction decision turns out to be wrong it can be redone offline
against those bytes instead of by re-crawling a university's server. That is what
made fixing an HTML-entity bug across 1,127 URLs cost one second rather than 61
requests.

---

### `_files/index.json` lives in the repo, not on Drive

There is a copy of `index.json` in the Drive folder from before this file was
committed. **Do not restore it.** Copy the PDFs across and leave the index alone.

The Drive copy is the older, thinner form: it has `linked_from` as bare URLs and
no `sources`, so restoring it over the repo copy silently removes the mapping
from every PDF back to the documents that link it, and nothing would fail to
tell you. The repo copy is the one that is kept up to date, because
`--stage merge` rewrites it every run.

The safe move is to delete `index.json` from the Drive folder so there is one
copy of it and no way to pick the wrong one. If it stays there, restoring PDFs
should be a file-type copy of `*.pdf`, never a folder sync.

## 9. Summary for developers

| Need | Go to | Command |
|---|---|---|
| Embed clean CUET pages and notices | `engine/corpus/cuet/` | `python -m engine.crawler.cuet --stage merge` |
| Rebuild after pulling | `engine/corpus/cuet/` | same as above, no network |
| Extract raw crawled pages | `engine/data/sites/<site>/<run>` | `uv run engine extract --run data/sites/...` |
| Check the corpus is sound | `engine/corpus/cuet/` | `python -m engine.crawler.cuet --stage verify` |
| See who owns which slice | — | `python -m engine.crawler.cuet --list-portions` |
| Inspect downloaded PDFs | `engine/corpus/cuet/_files/` | download from Drive if missing |
| Understand a scraping rule | `engine/src/engine/crawler/cuet/config.py` | read it; the reasons are next to the values |
