# CUET Scraper: Progress Log

## 8 September 2026

### What was done

- Studied the CUET website (`cuet.ac.bd`) to understand how it works
- Found out it's a Next.js app where the pages don't have any content in the HTML: everything comes from a hidden JSON API
- Discovered 16 API endpoints (most were undocumented) by reading the site's JavaScript files
- Built a full Python scraper with 6 stages: fetch API → extract content → download files → convert to engine format → audit
- Ran the scraper and captured:
  - 234 documents (departments, news, events, notices, curricula, CMS pages)
  - 284 PDFs (~428 MB) from notices and department pages
  - Raw API responses saved for re-processing without re-crawling
- Wrote tests for path resolution, content extraction, and the capture pipeline
- Wrote two spec documents explaining the site's structure, quirks, and how the scraper handles them
- Created an inventory of everything that was fetched
- Set up the project with `pyproject.toml`, wired it to the engine's contracts (`CrawledPage`, `CleanDocument`)
- Output is ready for Team B to run `engine extract` on

### What was NOT done (left for Part 2)

- Research section pages
- Most notice types (only NOC was done)
- Administration pages
- APA (Annual Performance Agreement) section
- ~36 pages that need a real browser to render (the API doesn't cover them)

### Key decisions made

1. **API first, browser later** - since the API gives clean JSON, no need to render 500+ pages in a browser. Only ~36 pages actually need one.
2. **Notices grouped into index tables** - instead of 265 tiny one-liner documents that would crowd the vector search, notices are grouped by type into table documents.
3. **PDFs downloaded but gitignored** - they're ~428 MB, too large for Git. The structured text output is committed.
4. **1.5s delay between requests** - polite crawling with a student contact email in the user-agent.

## 9 September 2026

### What was done

- Fixed news and event content extraction so records with empty description bodies (news 149, 150, event 137) are preserved with headline bodies, dates, and metadata instead of being discarded
- Preserved conference URLs in event records (ecce2027, icace, iciurp) in both document bodies and discovered page registries
- Fixed and calibrated headless browser capture settings:
  - Raised empty render threshold from 4,500 to 13,000 characters to reject chrome-only incomplete renders
  - Replaced faulty anchor-count condition with an explicit 8.0s render delay
  - Disabled overlay removal heuristic to prevent news and event cards from being stripped
  - Set capture concurrency to 1 to prevent async request starvation
- Rendered and saved missing news and event listing pages (/news-events, /events, /student/events)
- Total captured documents increased from 234 to 237 with 0 errors in _meta/errors.json
- Expanded unit test suite to 89 tests covering render thresholds, headline fallback, and conference URLs

