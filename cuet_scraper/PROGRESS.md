# CUET Scraper — Progress Log

## 8 September 2026

### What was done

- Studied the CUET website (`cuet.ac.bd`) to understand how it works
- Found out it's a Next.js app where the pages don't have any content in the HTML — everything comes from a hidden JSON API
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

1. **API first, browser later** — since the API gives clean JSON, no need to render 500+ pages in a browser. Only ~36 pages actually need one.
2. **Notices grouped into index tables** — instead of 265 tiny one-liner documents that would crowd the vector search, notices are grouped by type into table documents.
3. **PDFs downloaded but gitignored** — they're ~428 MB, too large for Git. The structured text output is committed.
4. **1.5s delay between requests** — polite crawling with a student contact email in the user-agent.
