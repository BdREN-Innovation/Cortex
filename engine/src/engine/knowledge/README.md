# Team B — Knowledge

**You build this.** Every file in this folder is a stub that raises
`NotImplementedError`. The signature and docstring of each function are
the specification; the code is yours to write.

```bash
uv run python scripts/progress.py --detail   # what is left in your files
```

You own the biggest share by a wide margin — **24 of the 54 stubs**, most of
the files, and nearly all of the genuinely open decisions. Start early, and build in the order below
rather than by whichever file looks most interesting.

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
| Text full of cookie banners / nav / "related articles" | **Yours** — `selectors.drop`, §5 |
| A page's real content missing from `text` | **Yours** — `selectors.main`, §5 |
| A page you need isn't in `pages.jsonl` at all | Team A — scope, `max_depth`, `exclude_patterns` |
| `manifest.json` shows errors, or `pages_written` looks small | Team A |
| A PDF you need wasn't downloaded | Team A — `max_documents`, or an `exclude_patterns` rule eating it |

**If the bytes are on disk, it is yours to fix.** If they were never fetched, it
is theirs.

`CrawledPage` and `CleanDocument` live in `contracts/` and are **frozen after
day 3**. Raise changes before then.

---

## 4. The decisions are yours

Nothing is preinstalled beyond what the scaffold itself uses. **No library is
prescribed anywhere in this package** — which HTML parser, which PDF library,
which embeddings provider, how you chunk, what backs the vector store. Those
are the engineering judgements you are here to make, and they are most of the
value of the fortnight.

Each stub opens with the questions worth answering before you type anything.
Go and find out what exists, compare at least two options wherever the choice
matters, and be ready to defend the one you picked.

```bash
uv add <package>                       # then commit pyproject.toml AND uv.lock
```

### How to decide, rather than argue

You are the team with the most open choices and the fewest obvious answers.
Two things make those choices tractable:

**Extraction is a separate stage, so comparing parsers is free.** Same crawl,
two configs, two outputs, diff them:

```bash
uv run engine extract --run <run> --config configs/extract.a.yaml --out a.jsonl
uv run engine extract --run <run> --config configs/extract.b.yaml --out b.jsonl
```

**Team C produces numbers.** Chunk size, embedding model, refusal threshold —
none of these have a right answer in the abstract, and all of them have one for
your corpus. Get their harness running early and let it settle arguments.

Write down what you compared and why you chose what you chose. That reasoning
is part of the deliverable, not overhead.

### One constraint that is not yours to change

Embeddings come from a hosted API — nothing runs a model locally, because you
are on 8 GB laptops without GPUs. Which provider and which model are still
entirely your call.

---

## 5. Fixing a site the extractor gets wrong

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

## 6. Images

There are none. Team A does not download them — nothing in the pipeline can use
a PNG, since the embedders are text-only.

What you DO get, for about ten lines: `alt` text and `<figcaption>` are prose,
they are sitting in the HTML you already have, and they belong in the document
text. "Seat growth by plan tier over twelve months" is a real sentence about the
page. A one-word `alt="logo"` is chrome and should be dropped — judge by word
count, not string length.

---

## 7. What actually determines quality

Four things move the numbers more than anything else you will do. None of them
has a right answer you can look up.

**How you chunk.** It matters more than which embedding model you buy. Too
small and an answer straddles two chunks so neither scores well; too large and
the one relevant sentence is diluted by its neighbours. Sweep it against Team
C's dataset — do not guess.

**Whether the text is clean.** Chrome that leaks into `text` gets embedded,
retrieved, and returned to a user as an answer. Read your own output. Five
documents per site, end to end, is enough to find the problem.

**Where the refusal threshold sits.** Too low and the system invents answers to
questions the corpus cannot answer; too high and it refuses real ones. Team C
grades both, separately, and they are not equally bad — a confident wrong
answer costs more trust than a refusal.

**Whether citations are honest.** A citation must point at something the model
actually saw. If you truncate context to fit a budget, whatever you dropped
must drop out of the citations too.

---

## 8. Citations: shared with Team A, delivered by you

A citation is not decoration. It is the only way a reader can check that an
answer is true, and Team C grades it directly.

It is also the one requirement that runs the whole length of the pipeline, so
it is nobody's job alone:

| | |
|---|---|
| **Team A** | Captures the provenance in the first place. Nothing downstream can invent a source or repair one captured wrong. |
| **Team B (you)** | Carry it through extraction and chunking, store it with the vector, and put it in the answer. |
| **Team C** | Grades whether the citations are real and whether they point at what was actually used. |

**Agree with Team A in week one what a citation has to show a reader**, then
work backwards together to what has to be captured for that to be possible.
Doing this in week three means a re-crawl.

### Why it has to be in the store

Here is the constraint that makes this a design decision rather than an
afterthought: **when you search, all you get back is what the vector store gave
you.** The answering layer has no other source. If a search result cannot tell
you where the text came from, you cannot cite it — and no amount of cleverness
downstream will recover the information.

So whatever a citation needs has to be stored *with* the vector, at index time.

Two ways teams get this wrong, both of which look fine until late:

* **Storing the text and nothing else.** Retrieval works, answers read well,
  and every citation is empty. You will only notice when Team C starts grading.
* **Planning to look it up afterwards** — search returns an id, then read
  `documents.jsonl` to fill in the details. It works on your laptop today, and
  it breaks the moment the index outlives the files it was built from, or
  somebody queries it from anywhere else. The index should be self-sufficient.

`Chunk` and `Citation` in `contracts/` already say what a reference consists
of — a stable id, where it came from, and enough human-readable context that a
person can find the passage on the page. Decide for yourself how that gets into
the store and back out again; just make sure it survives the round trip.

**The test to hold yourself to:** take one search result, close every other
file, and produce a complete citation from it alone. If you cannot, the
reference is not in the store yet.

### And it has to reach the final answer

Storing it is not the finish line. **`engine ask` must return the citations
alongside the answer text** — that is the deliverable, and it is what a user and
Team C both see.

Two things make a citation honest rather than decorative:

* It points at something the model **actually read**. If you dropped chunks to
  fit a context budget, those references drop too.
* It is specific enough to be checked. A reader should be able to follow it and
  find the passage, not just the site.

A refusal carries no citations, and that is correct — there was nothing to
cite.

---

## 9. Definition of done

- [ ] `engine extract` runs clean on every site Team A delivers
- [ ] You have read the `text` of five documents per site and found no chrome
- [ ] A written record of the choices you made — parser, embedder, chunking,
      vector store — and the comparison behind each one
- [ ] `target_tokens` chosen against Team C's dataset, not guessed
- [ ] A live Qdrant Cloud collection, with `engine ask` answering against it
- [ ] A single search result carries everything a citation needs — no second
      lookup, no other file open
- [ ] Answers carry citations that point at what the model actually read, and
      unanswerable questions are refused

---

Config reference: [configs/README.md](../../../configs/README.md) — how the four
config types map to the pipeline stages, plus a worked end-to-end example.
