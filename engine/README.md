# Cortex Engine

Crawl a website, build a RAG knowledge base over it, and score the result against a
golden dataset. Three teams, one folder, **no backend required** — everything runs
from the command line.

```
crawl  ──▶ documents.jsonl ──▶  index  ──▶ vector index ──▶  ask   ──▶ answer + citations
                                                       └──▶  eval  ──▶ scorecard
```

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv installs the interpreter).

```bash
cd engine
uv sync --extra dev          # creates .venv and installs everything
uv run pytest -q             # 30 tests, no network or API key needed
```

Try the full pipeline against the bundled fixture site:

```bash
# serve the 4-page demo site
python3 -m http.server 8765 --directory tests/fixtures/site &

uv run engine crawl --config configs/crawl.acme.yaml
uv run engine index --documents data/documents/acme/<run>/documents.jsonl --site acme
uv run engine ask "how long do refunds take" --index data/index/acme/<id>
uv run engine eval --dataset datasets/acme/golden.v1.yaml --index data/index/acme/<id>
```

Nothing above needs an API key: the default embedder is a deterministic local
hash and the default "generator" returns the retrieved passages verbatim.

## The three teams

| Team | Owns | Produces | Consumes |
|---|---|---|---|
| **Crawler** | `src/engine/crawler/` | `data/documents/<site>/<run>/documents.jsonl` | a URL |
| **Knowledge** | `src/engine/knowledge/` | a vector index + a `Retriever` | `documents.jsonl` |
| **Evaluation** | `src/engine/evaluation/`, `datasets/` | `data/runs/<id>/report.md` | a `Retriever` |

They integrate through **files with frozen schemas**, never by importing each
other's modules. `src/engine/contracts/` is the only shared surface, and
`CODEOWNERS` requires all three teams to review a change there.

**Nobody is blocked waiting for anyone.** `tests/fixtures/` holds a working
4-page site and `tests/test_evaluation.py` holds a `StubRetriever`, so teams 2
and 3 can build and test everything before the real crawler or index exists.

## Contracts

`CleanDocument` is the one to get right — the crawler can be rewritten freely as
long as it keeps emitting this:

| Field | Why it matters |
|---|---|
| `doc_id` | Stable hash of the canonical URL. The eval dataset references these. |
| `canonical_url` | Collapses `/page`, `/page/`, `/page?utm_source=x`, `/page#a` into one document. |
| `text` | Clean prose. Nav, footers and scripts already stripped. |
| `content_hash` | Skip re-embedding unchanged pages; `validate()` fails if it drifts from `text`. |
| `section_path` | Breadcrumb such as `["Home","Docs","Billing"]`. **Citations depend on it.** |
| `html_path` | Pointer into `data/raw/` so extraction can be re-run without re-crawling. |

`Retriever` (a `Protocol`) is the knowledge → evaluation seam. `Answer` carries
`citations` and a `refused` flag, both of which are graded.

## Commands

| Command | What it does |
|---|---|
| `engine crawl --config configs/crawl.<site>.yaml` | Fetch a site → `documents.jsonl` + `manifest.json` |
| `engine index --documents <path> --site <name>` | Chunk → embed → save a vector index |
| `engine ask "<question>" --index <dir>` | Retrieve, answer, print sources |
| `engine eval --dataset <yaml> --index <dir>` | Score against the golden set → `report.md` |

`engine eval --min-pass-rate 0.7` exits non-zero below the threshold, so CI can
gate a regression.

## Providers

| Role | Options | Notes |
|---|---|---|
| Embedding | `hash` (default), `openai` | **Anthropic has no embeddings endpoint** — generation only. |
| Generation | `extractive` (default), `openai`, `anthropic` | Keys via `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, matching the Cortex backend. |

`hash` is a lexical approximation with no semantic understanding. It exists so
the pipeline runs offline and in CI. **It is not a serious retriever** — see below.

## The baseline, and what it already tells us

Running the bundled dataset against the default `hash` + `extractive` stack:

```
pass rate        58.3%      recall@5   1.000      answer_match        0.778
  answerable     77.8%      recall@1   0.556      citation_precision  0.407
  unanswerable    0.0%      mrr        0.722
hallucination   100.0%
```

Two findings, both real:

1. **`recall@5` is perfect but `recall@1` is 0.556** — the right page is always
   retrieved, just not always ranked first.
2. **Every unanswerable question got answered.** Sweeping the refusal threshold
   shows there is *no* usable operating point with lexical embeddings:

   ```
    min_score |   pass | answerable | unanswerable |  halluc
         0.05 | 58.3% |     77.8% |        0.0% | 100.0%
         0.15 | 33.3% |     33.3% |       33.3% |  66.7%
         0.30 | 25.0% |      0.0% |      100.0% |   0.0%
   ```

   You either answer everything or refuse everything. The cause is visible in
   one query: *"Which payment cards are accepted?"* scores **0.0000** against the
   page containing "Visa, Mastercard and American Express", because the question
   and the answer share no literal token.

That is the argument for real embeddings, made with numbers rather than opinion —
which is exactly what the harness is for. Re-run it after switching to
`--provider openai` and the same table shows what changed.

```bash
uv run python scripts/sweep.py --index <dir> --dataset <yaml> --knob min_score
```

## Layout

```
engine/
├── configs/            crawl / index / eval YAML (committed, per site)
├── datasets/           golden Q&A sets (committed, reviewed in PRs)
├── data/               ALL runtime artifacts (gitignored)
│   ├── raw/            html as fetched
│   ├── documents/      documents.jsonl + manifest.json
│   ├── index/          vectors.npy + chunks.jsonl + index_meta.json
│   └── runs/           report.json + report.md
├── scripts/            sweep.py and other ops helpers
├── src/engine/
│   ├── contracts/      shared schemas — change by cross-team review only
│   ├── crawler/        fetcher, frontier, extract, pipeline
│   ├── knowledge/      chunking, embedding, store, retriever, indexer, rag
│   ├── evaluation/     dataset, metrics/, runner, report
│   └── cli/            argparse wrappers, no logic
└── tests/              30 tests incl. a live HTTP server over fixtures/site
```

## Writing the golden dataset

`datasets/<site>/golden.v1.yaml`. Rules the loader enforces:

- every answerable case needs `relevant_doc_ids` or `expected_answer_contains`
- an unanswerable case must not list `relevant_doc_ids`
- **the dataset is rejected if every case is answerable** — without unanswerable
  cases you are not measuring hallucination at all

50–80 cases beats 500. Bump to `golden.v2.yaml` rather than editing history, so
old scorecards stay comparable.

## Crawling responsibly

`robots.txt` is obeyed, requests are rate-limited per host (1 s default), a real
User-Agent is sent, and retries back off on 429/5xx. `obey_robots: false` exists
for sites you own. Keep `max_pages` set — it protects the target as much as you.

## Notes for later

- **Scaling the store.** `NumpyVectorStore` is exact brute-force cosine; fine for
  tens of thousands of chunks. Outgrow it by implementing the same three methods
  against pgvector — nothing above `store.py` changes.
- **Wiring into the app.** Nothing here imports Django. When the time comes, the
  seam is a management command or Celery task calling
  `engine.knowledge.rag.answer()`.
