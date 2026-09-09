# Cortex Data Inventory & Guide

A centralized reference explaining where scraped data lives across the repository, how each dataset is structured, and how the downstream pipeline teams (Team B: Knowledge/Extraction & Embeddings; Team C: Evaluation) should consume them.

---

## 1. High-Level Data Map

Data in Cortex is organized into two primary categories based on its lifecycle and purpose:

| Site | Location | Type | What's Included | Primary Format |
|---|---|---|---|---|
| **CUET** | [`engine/corpus/cuet/`](file:///c:/Users/User/Cortex/engine/corpus/cuet) | **Curated Reference Corpus** | Pre-processed Markdown, clean API text, HTML triples, per-portion shards | `.md`, `.json`, `.html`, `documents.jsonl`, `pages.jsonl` |
| **BDREN** | [`engine/data/sites/bdren/bdren-20260909T110121Z/`](file:///c:/Users/User/Cortex/engine/data/sites/bdren/bdren-20260909T110121Z) | **Crawler Runtime Run** | Crawled web pages, raw HTML snapshot, downloaded PDFs | `raw/*.html`, `docs/*.pdf`, `manifest.json`, `pages.jsonl` |
| **BUBT** | [`engine/data/sites/bubt/bubt-20260908T220949Z/`](file:///c:/Users/User/Cortex/engine/data/sites/bubt/bubt-20260908T220949Z) | **Crawler Runtime Run** | 100+ crawled web pages, raw HTML, routines & academic PDFs | `raw/*.html`, `docs/*.pdf`, `manifest.json`, `pages.jsonl` |
| **Green Univ.** | [`engine/data/sites/green/green-20260908T220124Z/`](file:///c:/Users/User/Cortex/engine/data/sites/green/green-20260908T220124Z) | **Crawler Runtime Run** | Crawled pages snapshot, raw HTML | `raw/*.html`, `manifest.json`, `pages.jsonl` |

---

## 2. CUET Corpus (`engine/corpus/cuet/`)

The CUET capture is an **API-first, pre-structured reference corpus**. Roughly 530+ of the documents were harvested directly from CUET's internal JSON API (with headless browser rendering used only for residual pages like listings).

### Directory Layout
```
engine/corpus/cuet/
├── _cms/                     # Core CMS pages (History, Vision, Campus Life, Research)
├── academic/                 # Departments, faculties, institutes, curricula
├── admission/                # Admission notices & scholarships
├── home/                     # Student organizations & campus clubs
├── news-events/              # News items (news/) and event details (event-details/)
├── top-bar/                  # Notices (NOC, general circulars)
├── _shards/                  # Committed per-portion shards (source of truth)
├── _meta/                    # Scraper run metadata, endpoints, and audit logs
├── _files/                   # Downloaded PDFs (gitignored — see Google Drive below)
├── documents.jsonl           # CleanDocument rows (rebuilt via merge)
├── pages.jsonl               # Crawled page records (rebuilt via merge)
├── manifest.json             # Dataset manifest (rebuilt via merge)
└── README.md                 # Dedicated CUET corpus documentation
```

### Key Instructions for Team B (Embedding & Knowledge)
1. **Rebuilding the index files**:
   `documents.jsonl`, `pages.jsonl`, and `manifest.json` are generated from `_shards/` so that concurrent scrapers don't conflict on git:
   ```bash
   cd engine
   uv run python -m engine.crawler.cuet --stage merge
   ```
2. **No boilerplate stripping needed for API docs**:
   Documents where `source == "api"` are already clean text—do not write heuristic selectors to strip navigation headers or cookie footers; they do not exist.
3. **Pass `--min-text-chars 50`**:
   Default extraction filters drop docs < 200 characters. CUET has legitimate notices and curriculum entries shorter than 200 chars. Use `--min-text-chars 50` so these are not dropped.
4. **Citations & Keys**:
   - Cite `url` (always points to a real public page on `cuet.ac.bd`).
   - Derive vector IDs from `page_id` / `doc_id`.

---

## 3. Multi-Site Crawl Runs (`engine/data/sites/`)

These folders represent the standard runtime artifact format defined by the Cortex CLI (`engine crawl` and `engine extract`).

### Directory Layout
Each site run is timestamped (`<site>-<YYYYMMDDTHHMMSSZ>/`) and adheres to the Cortex Team A -> Team B contract:
```
engine/data/sites/<site>/<site>-<timestamp>/
├── manifest.json             # Run summary: duration, status, URLs crawled, file counts
├── pages.jsonl               # Team A deliverable: page URLs, hashes, content types, status
├── raw/                      # Raw HTML snapshots named by xxhash (<hash>.html)
└── docs/                     # Downloaded non-HTML assets (e.g. notices, routine PDFs)
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

### How Team B Extracts These Runs
Feed any run directly into the extraction pipeline:
```bash
cd engine
uv run engine extract --run data/sites/bubt/bubt-20260908T220949Z
uv run engine extract --run data/sites/bdren/bdren-20260908T212837Z
uv run engine extract --run data/sites/green/green-20260908T220124Z
```

---

## 4. Heavy Assets & Google Drive Backup

Large binary files (PDFs, raw API dumps, and technical scraping specifications) are gitignored to keep the Git repository lightweight.

They are stored on Google Drive:
> **[📁 Cortex — Gitignored Data (Google Drive)](https://drive.google.com/drive/folders/1FhWXKBVmA1X_y4S0mvD5qgIQgtiZ7xVA)**

### Restore Mapping Table

| Drive Folder | Local Destination Path (from repo root) | Contents |
|---|---|---|
| `01_scraped_documents/*` | `engine/corpus/cuet/_files/` | 240+ CUET notice and circular PDFs (~428 MB) + `index.json` |
| `02_api_metadata/*` | `engine/corpus/cuet/_meta/` | Raw JSON API dump (`api_dump.json`, ~3.5 MB) |
| `03_scraper_specs/*` | `./` (repo root) | `CUET_SCRAPER_SPEC.md`, `CUET_SCRAPER_SPEC_PART2.md`, `SCRAPE_INVENTORY.md` |

---

## 5. Summary Matrix for Developers

| Need | Go To | Run Command |
|---|---|---|
| **Embed clean university pages & notices (CUET)** | `engine/corpus/cuet/` | `python -m engine.crawler.cuet --stage merge` |
| **Extract & chunk raw crawled pages (BUBT, BDREN, Green)** | `engine/data/sites/<site>/<run>` | `uv run engine extract --run data/sites/...` |
| **Inspect downloaded PDFs** | `engine/corpus/cuet/_files/` (or `engine/data/sites/<site>/<run>/docs/`) | Download from Google Drive if missing |
| **Review scraping rules & URL boundaries** | `engine/src/engine/crawler/cuet/` | `python -m engine.crawler.cuet --list-portions` |
