# Team A — Crawler

**You build this.** Every file in this folder is a stub that raises
`NotImplementedError`. The signature and docstring of each function are
the specification; the code is yours to write.

```bash
uv run python scripts/progress.py --detail   # what is left in your files
```

You are done when all 13 of your tests are green **and** you have captured 2–4
real sites.

---

## 1. What you own

Everything from *a URL* to *bytes on disk*. Fetch it, save it, record what you
found — and stop there.

You do **not** parse HTML for content, convert tables, or read PDFs. That is
Team B's `engine extract`. The split means an extraction change never costs you
a re-crawl, and your crawl never blocks their work.

Your deliverable, one folder per site per run:

```
data/sites/<site>/<run>/
├── pages.jsonl     ← one CrawledPage per URL. NO TEXT.
├── manifest.json   ← counts, errors, what was captured
├── raw/            ← html exactly as fetched
├── docs/           ← PDFs and other linked files, as fetched
└── images/         ← downloaded for later; nothing consumes them today
```

---

## 2. Build order

Each file only depends on the ones above it, so you are never blocked on your
own unfinished work.

| # | File | What it does | Tests |
|---|---|---|---|
| 1 | `fetcher.py` | HTTP with manners: robots, rate limit, retries | 1 |
| 2 | `frontier.py` | URL canonicalisation, scope rules, the queue | 2 |
| 3 | `discover.py` | Find links, linked files and images in HTML | 1 |
| 4 | `pipeline.py` | Chain them together, write the artifacts | 4 |

```
seeds ─▶ frontier ─▶ fetcher ─▶ discover ─▶ pipeline ─▶ pages.jsonl
           ▲                        │                     + raw/ docs/ images/
           └──── new links ─────────┘
```

**Start with `canonicalize()` in `frontier.py`.** It is six lines of test and
the highest-leverage function you own — it is what stops `/pricing`,
`/pricing/`, `/pricing?utm_source=x` and `/pricing#plans` becoming four copies
of one page in the search index.

### Libraries

**Nothing is preinstalled beyond PyYAML and numpy — these are suggestions, and
the choice is yours.** Add what you settle on with `uv add <package>`, then
commit `pyproject.toml` and `uv.lock` together so the rest of the team gets it
with a `uv sync`.

| Library | For | Notes |
|---|---|---|
| `requests` | all HTTP | Use a `Session` — connection reuse, one place for headers |
| `urllib.robotparser` | robots.txt | Stdlib. `RobotFileParser.can_fetch()` does the whole job — do not hand-roll it |
| `urllib.parse` | URL work | `urlparse`, `urlunparse`, `parse_qsl`, `urlencode`, `urljoin` |
| `beautifulsoup4` + `lxml` | finding links | Structural only — leave article text to Team B |
| `collections.deque` | the queue | `popleft()` is O(1); `list.pop(0)` is not |

Worth reading about, not necessarily using: **scrapy** (a full crawling
framework — more structure than this project needs, but read how it models a
scheduler and duplicate filter), **httpx** (async; only if you have *measured*
that requests is your bottleneck, which it will not be at 200 pages with a 1s
delay).

---

## 3. Politeness is not optional

An impolite crawler gets **the whole team's IP blocked** on the first serious
run, and you cannot un-block it before the deadline.

- `obey_robots: true` on every site you do not own. No exceptions.
- `delay_seconds >= 1.0`, per host.
- A real `User-Agent` that identifies the project.
- Retry `429/502/503/504` with backoff and honour `Retry-After`. Never retry a 404.
- Cap response sizes. Stream binaries; do not read a surprise 2 GB file into an
  8 GB laptop.

If a site blocks you, stop and tell the team. Do not "work around" it.

---

## 4. Four people, four sites, no merge conflicts

**Each of you owns one file: `configs/crawl.<yoursite>.yaml`.** Nobody edits a
shared module, so there is nothing to merge at the end — there was only ever one
crawler, driven four different ways.

Do **not** write `scrape_site1.py`, `scrape_site2.py`. Four scripts means four
sets of bugs, four robots.txt implementations, and a painful merge in week three.

```bash
cp configs/crawl.example.yaml configs/crawl.mysite.yaml
uv run engine crawl --config configs/crawl.mysite.yaml
```

Start with `max_pages: 20` while you tune. Raise it once the capture is clean.

| Problem | Fix |
|---|---|
| Crawling into junk (search, cart, login, calendars) | `exclude_patterns` |
| Missing pages that exist | raise `max_depth`, add seeds, loosen `include_patterns` |
| Getting rate-limited or blocked | raise `fetch.delay_seconds` |
| A huge PDF library swamping the run | `assets.max_documents` |
| Missing a whole section | add it to `seeds` — sitemap URLs make good seeds |

**Content problems are not yours.** Cookie banners and nav menus in the
*extracted text* are fixed with `selectors` in Team B's
`configs/extract.<site>.yaml`. Tell them; do not work around it in the crawl.

> **Trap:** `exclude_patterns` also applies to linked files. A `"\.pdf$"` rule
> silently switches off the entire PDF pipeline.

---

## 5. Three things that are easy to get wrong

**One bad page must never kill a run.** Wrap the fetch, append to `errors`, and
carry on. A crawl that dies at page 180 of 200 has produced nothing.

**No thin-page filter and no duplicate-text detection here.** Both need the
text, and there is no text at this stage. `/` and `/index.html` will both be
captured; Team B collapses them. Do not dedupe on raw HTML — identical pages
routinely differ by a timestamp or a CSRF token.

**Queue linked files at depth 0.** A PDF is a leaf, not another hop, so it
should not be dropped for sitting one level too deep. Domain and
include/exclude rules still apply to it.

---

## 6. Syncing with Team B

Hand them **the path to a run directory**. That is the whole interface.

They run `engine extract --run <your run dir>` against it. You can run that
yourself too — it is free and offline — and you should, because it is how you
see what they will see:

- Content missing from `documents.jsonl` but present in `raw/` → **their** problem
- Content missing from `raw/` too → **your** problem

`CrawledPage` in `contracts/` is the shared schema and is **frozen after day 3**.
Changing it costs all three teams a re-run, so raise it before then.

Every record must satisfy `CrawledPage.validate()`:

| Field | Requirement |
|---|---|
| `page_id` | Stable hash of `canonical_url`. Team C's dataset references these |
| `canonical_url` | Non-empty, canonicalised |
| `content_path` | Points at a file that **actually exists** in the run directory |
| `content_type` | `text/html`, `application/pdf`, … — Team B routes on this |
| `parent_url` | On a linked file: the page that linked it. Its breadcrumb gets inherited |

---

## 7. Definition of done

- [ ] 2–4 sites, one committed `configs/crawl.<site>.yaml` each
- [ ] Every site captures cleanly at its full `max_pages`
- [ ] `manifest.json` shows `errors: []` — or every error is explained in your handover
- [ ] Every `content_path` resolves to a real file
- [ ] You ran `engine extract` once per site and sanity-checked the output
- [ ] `delay_seconds >= 1.0` and `obey_robots: true` on every site you do not own
- [ ] A short handover note: which sites, what you excluded and why, what broke

---

Config reference: [configs/README.md](../../../configs/README.md) — how the four
config types map to the pipeline stages, plus a worked end-to-end example.
