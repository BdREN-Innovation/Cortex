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
└── docs/           ← PDFs and other linked files, as fetched
```

---

## 2. Build order

Each file only depends on the ones above it, so you are never blocked on your
own unfinished work.

| # | File | What it does | Tests |
|---|---|---|---|
| 1 | `fetcher.py` | HTTP with manners: robots, rate limit, retries | 1 |
| 2 | `frontier.py` | URL canonicalisation, scope rules, the queue | 2 |
| 3 | `discover.py` | Find links and linked files in HTML | 1 |
| 4 | `pipeline.py` | Chain them together, write the artifacts | 4 |

```
seeds ─▶ frontier ─▶ fetcher ─▶ discover ─▶ pipeline ─▶ pages.jsonl
           ▲                        │                     + raw/ and docs/
           └──── new links ─────────┘
```

**Start with `canonicalize()` in `frontier.py`.** It is six lines of test and
the highest-leverage function you own — it is what stops `/pricing`,
`/pricing/`, `/pricing?utm_source=x` and `/pricing#plans` becoming four copies
of one page in the search index.

### The decisions are yours

Nothing is preinstalled beyond what the scaffold itself uses. **No library is
prescribed** — which HTTP client, which HTML parser, how you model the queue,
these are the engineering judgements you are here to make.

The stub docstrings list the questions worth answering before you start typing.
Go and find out what exists, compare a couple of options, and be ready to say
why you picked what you picked. "It was in the README" is not an answer.

Add whatever you settle on with `uv add <package>`, then commit
`pyproject.toml` and `uv.lock` together so the rest of the team gets it with a
`uv sync`.

Two things that are not open questions, because they are about not getting
blocked or blocklisted rather than about design:

- **robots.txt has a parser in the standard library.** Writing your own is a
  day you do not have, and the edge cases are subtler than they look.
- **Politeness is non-negotiable** — see the next section.

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

## 6. Capture faithfully — Team B can only read what you saved

Team B turns your bytes into text, tables and parsed documents. They do that
work, not you. But **they can only extract what is actually in the file you
wrote**, and a page saved badly cannot be fixed downstream — it can only be
re-crawled.

So the quality of their text extraction depends on the fidelity of your
capture. Things that quietly destroy it:

* **Truncation.** A size cap that cuts a page in half loses the second half
  permanently, and nothing about the saved file says it was truncated.
* **Encoding.** Get the character set wrong and every accented character,
  currency symbol and dash becomes garbage in the extracted text. Servers lie
  about encoding in headers; the document often declares its own.
* **Content that is not in the HTML you received.** Plenty of sites render
  their main content with JavaScript after the page loads. What you save is an
  empty shell, and Team B extracts nothing from it — with no error to explain
  why. Check a saved page against what the browser shows before you trust a
  whole site.
* **Linked files never fetched.** A PDF you skipped is a document that does not
  exist as far as the rest of the pipeline is concerned.
* **Redirects and error pages saved as if they were content.** A 404 page has
  text on it, and it will happily be indexed as an answer.

**Open one of your saved files and read it.** Not `pages.jsonl` — the actual
HTML in `raw/`, and a downloaded PDF. Does it contain what the live page
contains? That check takes two minutes and it is the difference between Team B
debugging their extractor for a day and finding the problem in a minute.

The rule of thumb from §8 applies here too: if the content is missing from
`raw/`, it is your problem. If it is in `raw/` but missing from their output,
it is theirs.

**Team C will be reading your captures in week one.** They have no pipeline to
evaluate yet, so they spend the early weeks working with you and Team B — and
because they read the corpus as *content* rather than as a stage they own, they
are usually the first to notice that a section of the site is missing or that a
page came back empty. Take their reports seriously and early; a gap they find in
week one is a config change, and the same gap found in week three is a
re-crawl.

---

## 7. Citations start with you

The thing this system is judged on is not "did it answer" but "did it answer
**and show where the answer came from**". Team C grades that directly, and an
answer nobody can verify is worth very little.

Every part of a citation originates in what you capture. Team B carries it
through extraction, into the vector store and out into the answer — but they
can only carry what you gave them. Nothing downstream can invent a source, and
nothing downstream can repair one that was captured wrong.

Some of it is obvious: a page's address has to be correct and stable, or a
citation points somewhere that does not exist. Some of it is less obvious — a
PDF you downloaded has no page of its own, so how does a reader ever find their
way back to it? Think about what a person holding one of your records would
need in order to locate the original.

**This is a conversation to have with Team B in week one, not week three.**
Sit down together, work out what a citation on the finished product should show
a reader, and work backwards to what has to be captured for that to be possible.
Then make sure your records carry it.

You will know it worked when Team B can produce a complete, correct citation
without asking you for anything and without opening any file but their own.
Getting this wrong is expensive: it surfaces when Team C starts scoring, and
fixing it means re-crawling.

---

## 8. Syncing with Team B

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

## 9. Definition of done

- [ ] 2–4 sites, one committed `configs/crawl.<site>.yaml` each
- [ ] Every site captures cleanly at its full `max_pages`
- [ ] `manifest.json` shows `errors: []` — or every error is explained in your handover
- [ ] Every `content_path` resolves to a real file
- [ ] You have opened saved HTML and a saved PDF from each site and confirmed
      they contain what the live pages contain
- [ ] Agreed with Team B, in writing, what a citation needs — and your records
      carry all of it
- [ ] You ran `engine extract` once per site and sanity-checked the output
- [ ] `delay_seconds >= 1.0` and `obey_robots: true` on every site you do not own
- [ ] A short handover note: which sites, what you excluded and why, what broke

---

Config reference: [configs/README.md](../../../configs/README.md) — how the four
config types map to the pipeline stages, plus a worked end-to-end example.
