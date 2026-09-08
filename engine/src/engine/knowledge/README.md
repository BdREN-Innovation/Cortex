# Team B — Knowledge

**You build this.** Every file in this folder is a stub that raises
`NotImplementedError`. The signature and docstring of each function are
the specification; the code is yours to write.

```bash
uv run python scripts/progress.py --detail   # what is left in your files
```

You own the biggest share: **23 of the 43 tests** (20 of them run without
any optional extra; 3 parser tests need `uv add pdfplumber`). Start early, and build in the
order below rather than by whichever file looks most interesting.

---

## 1. What you own

Everything from *captured bytes* to *an answer with citations*.

```
pages.jsonl ─▶ extract ─▶ documents.jsonl ─▶ index ─▶ Qdrant ─▶ ask ─▶ answer + citations
  (team A)     ^^^^^^^^ yours from here ^^^^^^^^
```

---

## 2. Build order

| # | File | What it does | Tests |
|---|---|---|---|
| 1 | `extraction.py` | Saved HTML → title, prose, tables, breadcrumb | 5 |
| 2 | `pdf.py` | PDF bytes → text | — |
| 3 | `parsers.py` | Pick the PDF engine behind one interface | 5 |
| 4 | `documents.py` | `pages.jsonl` → `documents.jsonl` | 5 |
| 5 | `chunking.py` | Documents → overlapping chunks | 2 |
| 6 | `embedding.py` | Text → vectors | 2 |
| 7 | `store.py` | Vectors → NumPy, then Qdrant | 1 |
| 8 | `indexer.py` | Chain 5–7, write `index_meta.json` | — |
| 9 | `retriever.py` | The object Team C is handed | 1 |
| 10 | `rag.py` | Retrieve, ground, cite, refuse | 2 |

**Get 1–4 working before you touch anything else.** `engine extract` running end
to end unblocks your own iteration loop, and everything downstream is easier to
debug once you can see clean text.

---

## 3. Syncing with Team A

**Their deliverable is a run directory. That is the entire interface.**

```
data/sites/<site>/<run>/
├── pages.jsonl     ← one CrawledPage per URL: where it came from, what type,
│                     which file holds the bytes. NO TEXT.
├── manifest.json   ← counts, errors, what was captured
├── raw/            ← the HTML, exactly as fetched
└── docs/           ← PDFs and other linked files
```

You never call their code, never crawl, never touch the network in this stage.
You read `pages.jsonl`, open the files it points at, and write
`documents.jsonl` next to it.

### Why the split exists

Because **you will change your mind about extraction ten times**, and each of
those would otherwise mean asking Team A to re-crawl a live site. Instead:

```bash
uv run engine extract --run data/sites/acme/20260908T091500Z
```

Seconds, offline, as often as you like.

### Whose problem is it?

| Symptom | Whose |
|---|---|
| Text full of cookie banners / nav / "related articles" | **Yours** — `selectors.drop`, §6 |
| A page's real content missing from `text` | **Yours** — `selectors.main`, §6 |
| A page you need isn't in `pages.jsonl` at all | Team A — scope, `max_depth`, `exclude_patterns` |
| `manifest.json` shows errors, or `pages_written` looks small | Team A |
| A PDF you need wasn't downloaded | Team A — `max_documents`, or an `exclude_patterns` rule eating it |

**If the bytes are on disk, it is yours to fix.** If they were never fetched, it
is theirs.

`CrawledPage` and `CleanDocument` live in `contracts/` and are **frozen after
day 3**. Raise changes before then.

---

## 4. Libraries

**Nothing is preinstalled beyond PyYAML and numpy.** Everything below is a
suggestion; pick what suits you, `uv add` it, and commit `pyproject.toml` and
`uv.lock` together so the team stays in sync.

| Library | For | Notes |
|---|---|---|
| `beautifulsoup4` + `lxml` | HTML → text | `select_one(css)`, `decompose()`, `replace_with()` |
| `pypdf` | PDF → text | Baseline: ~10 ms/page, ~15 MB. Flattens tables |
| `pdfplumber` | PDF → text + tables | **Recommended.** ~100 ms/page, ~60 MB, pure Python |
| `numpy` | vectors | Normalise on the way in; `argpartition` for top-k |
| `qdrant-client` | vector store | Qdrant Cloud |
| `openai` | embeddings + generation | |
| `anthropic` | generation only | **No embeddings endpoint.** People try; it does not exist |

Also worth evaluating — measure before adopting:

- **trafilatura** / **readability-lxml** / **justext** — boilerplate removal.
  Can beat hand-tuned selectors on messy sites and lose badly on clean docs sites.
- **tiktoken** — real token counts. A ~4-chars-per-token estimate is fine for
  deciding where to cut.
- **langchain-text-splitters** — `RecursiveCharacterTextSplitter`. A hand-written
  paragraph splitter you understand will beat a library you cannot debug on day 12.
- **sentence-transformers** — good local embeddings on CPU, ~100 MB models.
  A real option if API budget is a problem.
- **docling** — see §5.

---

## 5. Choosing a PDF engine

```yaml
parser: pdfplumber   # or: builtin | docling
```

The setting picks the **PDF** engine only. HTML always goes through
BeautifulSoup, because the hard part of a web page is knowing which `<div>` is a
cookie banner — a per-site selector problem, not a parsing one.

| | `builtin` (pypdf) | `pdfplumber` | `docling` |
|---|---|---|---|
| Speed | ~10 ms/page | ~100 ms/page | seconds/page on CPU |
| Resident memory | ~15 MB | **~60 MB** | 2–4 GB |
| Install | none | 8 packages | **106 packages**, incl. torch + CUDA |
| Ruled tables | flattened to whitespace | **recovered as grids** | recovered |
| Scanned PDFs | nothing | nothing | **OCR** |

**Use `pdfplumber`.** On an 8 GB laptop with no GPU this is not a close call:
docling installs the entire CUDA stack that will never execute, then wants 2–4 GB
of RAM to run a layout model while you also have a browser and an editor open.

Two things to get right when you build it:

- **Memory.** pdfplumber caches every character object per page. Call
  `page.flush_cache()` after each page. On a 300-page PDF that is 366 MB
  without it versus 67 MB with it.
- **Reading order.** Walk the page top to bottom emitting prose-above-table,
  then the table. Do not append all tables after all prose — a table's meaning
  lives in the sentence immediately above it.

**Scanned PDFs** are the one case neither pypdf nor pdfplumber handles: no text
layer, so both return nothing. The pipeline already drops those as "thin" and
logs it. Check the extract logs around day 8; if it is one stray file, ignore
it. If it is a whole site's document library, that is a scoping conversation,
not a parser upgrade on an 8 GB laptop.

**Decide with evidence.** Extraction is a separate stage precisely so this is free:

```bash
uv run engine extract --run <run> --out builtin.jsonl    --config configs/extract.builtin.yaml
uv run engine extract --run <run> --out pdfplumber.jsonl --config configs/extract.pdfplumber.yaml
```

---

## 6. Fixing a site the extractor gets wrong

Config, not code — so nobody edits a shared module:

```yaml
# configs/extract.<site>.yaml
selectors:
  main: "#article-body"           # where the real content lives
  drop:                           # junk repeated on every page
    - ".cookie-banner"
    - ".related-articles"
  breadcrumb: ".crumbs"
```

`drop` runs first, so removed junk cannot contaminate the title or breadcrumb.

**The loop:** extract → open `documents.jsonl` → read three `text` fields end to
end → find the junk → add a selector → re-extract. Two seconds a lap.

---

## 7. Images

There are none. Team A does not download them — nothing in the pipeline can use
a PNG, since the embedders are text-only.

What you DO get, for about ten lines: `alt` text and `<figcaption>` are prose,
they are sitting in the HTML you already have, and they belong in the document
text. "Seat growth by plan tier over twelve months" is a real sentence about the
page. A one-word `alt="logo"` is chrome and should be dropped — judge by word
count, not string length.

---

## 8. The decisions that actually determine quality

**`target_tokens` matters more than your embedding model.** Too small and an
answer straddles two chunks so neither scores well; too large and the one
relevant sentence is diluted by 300 tokens of neighbours. Sweep it against Team
C's dataset — do not guess.

**`hash` is not a real retriever.** It is deterministic bag-of-words with no
semantic understanding: "refund" and "reimbursement" are unrelated to it. It
exists so the pipeline runs offline with no API key, which is what lets you and
Team C work before billing is set up. Build with it; ship with `openai`.

**Develop against `backend: numpy`.** Exact, no service, fast enough to be
invisible at this corpus size. Switch to Qdrant when you are integrating, not
while you are iterating on chunk size.

**Qdrant Cloud credentials go in `engine/.env`, never in `configs/`** — configs
are committed. Derive point IDs from `chunk_id` so re-indexing replaces rather
than duplicates. Deleting `data/index/` does *not* delete the collection.

**Refusal is graded.** An unanswerable question answered fluently and cited
confidently is the worst thing this system can produce. `min_score` is the knob:
too low and you hallucinate, too high and you refuse real questions.

---

## 9. Definition of done

- [ ] All 23 of your tests green
- [ ] `engine extract` runs clean on every site Team A delivers
- [ ] You have read the `text` of five documents per site and found no chrome
- [ ] A documented parser choice, backed by output you actually compared
- [ ] `target_tokens` chosen against Team C's dataset, not guessed
- [ ] Real embeddings (`openai`) in the demo path, not `hash`
- [ ] A live Qdrant Cloud collection with `engine ask` answering against it
- [ ] Answers carry citations, and unanswerable questions are refused

---

Config reference: [configs/README.md](../../../configs/README.md) — how the four
config types map to the pipeline stages, plus a worked end-to-end example.
