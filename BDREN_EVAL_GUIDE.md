# BdREN Evaluation — Work Log & Guide


## 1. Who did what 

| Area | Owner | What | Verified this session? |
|---|---|---|---|
| Evaluation package implementation | **Tasmia** | `metrics/retrieval.py`, `metrics/answer.py`, `dataset.py`, `runner.py`, `report.py` — all 5 were empty stubs, built from scratch | Yes — `scripts/progress.py` confirmed 19/19 (100%) after implementation, and each metric function unit-tested against hand-built cases before committing |
| Golden dataset v1 — initial 68 cases | **Tasmia** | `datasets/bdren/golden.v1.yaml` — authored from `documents.jsonl`, 8 of 9 shapes covered, 20.6% unanswerable | Yes — `load_dataset()` confirmed 68 cases with 0 validation errors; every unanswerable case confirmed via 2-3 `--grep` passes with increasingly specific phrasing before labeling |
| PDF extraction gap — root cause found | **Tasmia** | Confirmed 0 of 228 documents in the team's own indexed BdREN corpus (`scratch/corpus/bdren/`) are `doc_type=pdf`, despite `pdf.py` being fully implemented (pymupdf/pdfplumber/OCR) | Yes — traced to `pages.jsonl` never receiving a PDF entry from the crawler, so `extract_documents()` never calls the PDF parser at all; flagged to the team before this session's fixes began |
| Cross-team Git coordination | **Tasmia** | Merged `team-a/scrapers` and `team-b` into local `team-c/evaluation` branch without touching `main`; resolved `pyproject.toml`/`uv.lock` merge conflicts; set up Git LFS to pull large crawl archives (bdren.zip, ~592 MB) | Yes — `uv run python scripts/progress.py` confirmed 297/311 (95%) immediately after merge, before any Team C code was written |
| Eval pipeline crash fixes | **Mifta** | `write_report`, `EvalConfig.from_dict` — both missing entirely, both blocked `engine eval` from running at all | Yes — traced the crashes, wrote the fixes, re-ran successfully |
| Qdrant indexing fix | **Mifta** | `QdrantStore` had no client timeout, failed on any upsert batch over ~50 chunks — Team B's file, fixed to unblock eval, flagged for their review | Yes — reproduced the timeout, applied the fix, confirmed batches succeed |
| BdREN eval configs | **Mifta** | `configs/index.bdren.yaml`, `configs/eval.bdren.yaml`, `configs/eval.bdren.k10.yaml` | Yes |
| Golden dataset — unanswerable coverage | **Mifta** | Added 4 cases to `golden.v1.yaml` (68→72 cases, hit the 25% unanswerable target exactly) | Yes |
| Golden dataset — label corrections | **Mifta** | `golden.v2.yaml` — corrected `expected_answer_contains` on cases 009, 013; confirmed 72 cases (case-count check run twice, both times printed `72`) | Yes |
| Diagnostic scripts | **Mifta** | `scripts/check_unused.py`, `scripts/rank_check.py` — both run, output seen directly. `scripts/context_check.py`, `scripts/retrieval_diagnostic.py` — created and committed, not run in this session | Partial — 2 of 4 confirmed running |
| Gemini generation retry | **Mifta** | `knowledge/rag.py` — retry/backoff on Gemini 429s | Yes — `gemini busy ... retrying in 15s` / `30s` lines fired live during the hybrid eval run, and the run completed instead of crashing |
| Hybrid search (chunks.jsonl + BM25) | **Mifta** | `knowledge/indexer.py` — writes `chunks.jsonl`, enabling dense+keyword hybrid retrieval | Yes — file confirmed on disk (453 lines), and the retriever's own log line confirmed loading it: `loaded 453 chunks for BM25 from data\index\bdren\1c1e0d7984fd\chunks.jsonl` |
| Full BdREN index build | **Mifta** | 174-document corpus → 453 chunks, Qdrant collection `bdren-v1`, index id `1c1e0d7984fd` | Yes |
| Two real eval runs | **Mifta** | Dense (Gemini) and hybrid, both against the full index — first time this pipeline was run end-to-end for BdREN | Yes — full terminal transcripts for both, including the hybrid run's per-request logs |
| Committed and pushed to `team-c/evaluation` | **Mifta** | 3 commits: Team C's own files; the cross-team fix to Team B's files (flagged "please review" in the message); `golden.v2.yaml` + `smoke.yaml` | Yes — full `git status`/`git push` sequence confirmed clean at each step, `.env` confirmed never staged |


---

## 2. What's where

| Thing | Location | Notes |
|---|---|---|
| BdREN documents (source for eval questions) | `data/sites/bdren/bdren-20260913T073128Z/documents.jsonl` | 174 documents. Extracted via `engine.knowledge.bdren.bdren_extraction`, not the shared `engine extract` pipeline (per `DATA_GUIDE.md` §7 — BdREN has its own extractor) |
| Golden dataset v1 — original 68 cases | `datasets/bdren/golden.v1.yaml` (before Mifta's 4-case addition) | Authored by Tasmia against `documents.jsonl` (180-doc extraction via the shared `engine extract` pipeline, before the switch to `bdren_extraction.py`'s 174-doc count) |
| Golden dataset v1 | `datasets/bdren/golden.v1.yaml` | 72 cases, 25.0% unanswerable. The version actually used for both eval runs in §4 |
| Golden dataset v2 | `datasets/bdren/golden.v2.yaml` | 72 cases (confirmed), cases 009/013 corrected. **Not yet run through `engine eval`** — v1 is still the one with real scorecards behind it |
| Smoke test set | `datasets/bdren/smoke.yaml` | Contents not reviewed in this session — check before relying on it |
| Index configs | `configs/index.bdren.yaml` | `backend: qdrant`, `embedding_provider: cohere`, `embedding_model: embed-multilingual-v3.0` — multilingual chosen deliberately, since BdREN has at least one Bangla page (`/news?page=13`, per `DATA_GUIDE.md`'s known-gaps note) |
| Eval configs | `configs/eval.bdren.yaml`, `configs/eval.bdren.k10.yaml` | k10 config is the one used for both real runs (`top_k: 10`) |
| Full index | Qdrant collection `bdren-v1`, index id `1c1e0d7984fd` | 174 docs / 453 chunks (`chunks.jsonl`, `index_meta.json`, `qdrant.json` all confirmed present on disk). Built across several smaller indexing calls (Cohere trial-tier rate limits forced splitting into ~4 batches of ~60 docs each) — all land in the same collection |
| Eval reports | `data/runs/<run_id>/report.json` + `report.md` | Hybrid run's report: `data\runs\20260920T180658Z\` |
| **⚠️ Corpus size correction** | — | `DATA_GUIDE.md` §7 states BdREN's `bdren-20260913T073128Z` run should have ~224 documents (matching the `bdren-20260911T042956Z` run's 224). **The actual extracted count for the 0913 run is 174.** Not yet reconciled — worth checking with whoever wrote that section of `DATA_GUIDE.md` before trusting either number blindly. |

---

## 3. How to reproduce

```bash
cd engine

# Confirm the index exists and is queryable (no re-embedding, just a sanity check)
uv run engine ask "What is BdREN's annual report for 2024?" --index data/index/bdren/1c1e0d7984fd

# Re-run the dense eval (the 0.861 pass-rate / 0.000 hallucination result in §4)
uv run engine eval \
  --dataset datasets/bdren/golden.v1.yaml \
  --index   data/index/bdren/1c1e0d7984fd \
  --config  configs/eval.bdren.k10.yaml

# Re-run the hybrid eval (the 0.889 pass-rate / 0.056 hallucination result in §4)
$env:RETRIEVAL_MODE = "hybrid"     # PowerShell; use `export` on macOS/Linux
uv run engine eval \
  --dataset datasets/bdren/golden.v1.yaml \
  --index   data/index/bdren/1c1e0d7984fd \
  --config  configs/eval.bdren.k10.yaml
Remove-Item Env:RETRIEVAL_MODE
```

**Finding the latest report without typing the run-id by hand** (PowerShell —
useful since the run-id is a timestamp you won't remember):
```powershell
$latest = (dir data\runs | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
Select-String -Path "data\runs\$latest\report.md" -Pattern "hallucination"
```

**Credentials needed** (`engine/.env`, never commit): `QDRANT_URL`,
`QDRANT_API_KEY`, `COHERE_API_KEY` (embeddings — free trial tier is capped at
100 calls/min and 1,000 calls/month, worth checking your quota before a full
re-index), `GEMINI_API_KEY` (generation — `gemini-3.5-flash-lite` was used
here since `gemini-2.5-flash` is retired and `gemini-3.5-flash`'s free tier
caps at 20 requests/day, too low for a 72-case run). Expect occasional
`gemini busy (429 RESOURCE_EXHAUSTED)` warnings mid-run even on
`gemini-3.5-flash-lite` — the retry logic in `rag.py` handles these
automatically (waits 15s, then 30s) and the run completes; it's noisy in the
log but not a failure.

**Rebuilding the index from scratch**, if the collection is ever wiped: split
`documents.jsonl` into ~60-document chunks and index each separately with a
delay between (Cohere's per-minute token limit rejects the whole corpus in one
call), keeping `recreate_collection: false` after the first batch so later
batches add to the same collection instead of wiping it.

**Windows line-ending warnings during `git add`/`git commit`** (`LF will be
replaced by CRLF the next time Git touches it`) on `golden.v1.yaml`,
`context_check.py`, `rank_check.py`, `smoke.yaml` are harmless — Git
normalizing line endings on Windows, not a bug. If a teammate on Mac/Linux
later sees a diff on these files touching every line with no real content
change, this is why.

---

## 4. Eval results so far

Both runs below used `golden.v1.yaml` (72 cases) and the full 174-doc / 453-chunk
index (`1c1e0d7984fd`), so they're a clean apples-to-apples comparison —
retrieval mode is the only thing that changed between them.

| Metric | Dense (Gemini, top_k 10) | Hybrid (top_k 10) |
|---|---|---|
| Overall pass rate | 0.861 | 0.889 |
| Answerable questions passed | 0.815 | 0.870 |
| Unanswerable questions correctly refused | 1.000 | 0.944 |
| **Hallucination rate** | **0.000** | **0.056** |
| Mean recall@5 | 0.926 | 0.963 |
| Mean MRR | 0.731 | 0.778 |

**Hybrid retrieves better across the board — but at the cost of one new
hallucination.** `bdren_065` ("What is the annual membership fee for a private
university to join BdREN?") went from correctly refused (dense) to answered
anyway (hybrid). Confirmed straight from the failing-cases table in
`report.md`:

> `bdren_065` | What is the annual membership fee for a private university to
> join BdREN? | (refuse) | To join BdREN, private/public medical/dental
> colleges, national or international | `bdf7daf2d9f51e7d`, `3b299f539ff17a1b`,
> `5810f9b73d202f31` | system answered a question it should have refused
> (hallucination)

The retrieved chunk (`bdf7daf2d9f51e7d`) is `/member/category` — a page about
membership *eligibility categories*, not fee *amounts*. Keyword search
surfaced it on the words "membership," "fee," and "private university" even
though it doesn't actually contain the answer. Gemini treated it as sufficient
grounding and answered instead of refusing.

**Leading theory, not yet confirmed:** hybrid's rank-fusion scores sit on a
completely different scale than dense cosine scores (roughly 0.01–0.05 vs
0.5–0.7). `eval.bdren.k10.yaml`'s `rag.min_score` may still be tuned for
dense-mode scale, which would let a weakly-relevant hybrid match through that a
properly-tuned threshold would exclude. Worth checking `min_score` against
hybrid mode's actual score distribution before concluding hybrid search itself
is the problem.

**Decision needed, not yet made:** is +4 answerable-pass cases and better
recall/MRR worth −1 unanswerable-refusal correctness? That's a call for the
team, not something resolved unilaterally here.

### Retrieval position check (`scripts/rank_check.py`), hybrid mode

Run for five specific cases that were known to be retrieval trouble spots.
Confirmed output:

| Case | Doc | Position (hybrid) |
|---|---|---|
| `bdren_011` | `b2b6bf24c8657c18` | 5 |
| `bdren_014` | `de71e13b9659d02b` | not in top 50 |
| `bdren_017` | `a5da2048c06d9870` | not in top 50 |
| `bdren_040` | `e9ac3756197448df` | 7 |
| `bdren_052` | `8ae0b74645438950` | 3 |

`bdren_014` and `bdren_017` are still unfindable even with hybrid search —
see §5. `bdren_052` moving to position 3 and `bdren_011` to position 5 line up
with the recall/MRR gains in the table above.

---

## 5. Open findings — not yet fixed

- **Cases 014 and 017 can't be found by dense OR hybrid search.** Confirmed
  directly via `rank_check.py` (table above) — both show "not in top 50" even
  in hybrid mode. Working theory: their source content is table rows with no
  page-identity context in the chunk text (e.g. a partners-page row is just an
  institution name — neither "partners page" nor "member directory" appears in
  the chunk itself). Proposed fix: prepend each page's URL path to chunk text
  before embedding. Needs a chunker change, not attempted yet.
- **The live BdREN site contradicts itself on several numbers.** Bandwidth
  page says BUET has 600 Mbps / 34 public universities; a table elsewhere says
  3,000 Mbps / 45. Similar conflicts on the Others-category count and the
  partners-page total. Cases 014, 022, 051–053 are genuine source conflicts —
  the system currently has no rule for handling contradictory source data.
- **`require_citation: true` in `eval.bdren.yaml` is configured but never
  enforced.** `runner.py`'s scoring logic doesn't read this field at all — an
  uncited answer currently isn't failed for that reason, contrary to what the
  config comment says should happen.
- **`golden.v1.yaml`'s 4 newest unanswerable cases (bdren_069–072) were written
  from plausible topic-matching, not confirmed with `--grep` against
  `documents.jsonl` first.** Every other case in the file was verified this
  way; these weren't. Worth a quick pass before trusting them in a scorecard.
- **`--coverage` shows 174 of ~200+ documents with zero questions.** The
  dataset is topically real but thin relative to the corpus size — see
  `evaluation/README.md` §8 for the fuller breakdown.
- **`scripts/context_check.py` and `scripts/retrieval_diagnostic.py` are
  committed but not run in this session** — confirm what they do and that
  they still work before relying on them.
- **No unit tests yet** for `evaluation/`'s own files (`tests/evaluation/`).

---

## 6. Bugs fixed in shared (non-Team-C) files — flagged for review

These were blocking Team C's work, so they were fixed to unblock progress —
but they live in Team B's files and haven't been reviewed by Team B yet.
Pushed in a separate commit specifically so this is easy to review in
isolation: `f690cbb`, message *"Fix Qdrant client timeout + add Gemini retry +
hybrid search support (Team B's files — needed to unblock Team C's eval run,
please review)"*.

| File | Fix | Why |
|---|---|---|
| `knowledge/store.py` | `QdrantClient(...)` had no `timeout=`; added `timeout=120.0` and lowered default `batch_size` from 128 to 32 | Any upsert batch over ~50 chunks reliably timed out against the free-tier Qdrant cluster |
| `knowledge/rag.py` | Added retry/backoff on Gemini 429/503 responses | Needed to get a full 72-case run through without a rate-limit crash partway — confirmed firing live during the hybrid run |
| `knowledge/indexer.py` | Added a `chunks.jsonl` write, enabling hybrid (dense + keyword) retrieval mode | Prerequisite for the hybrid eval run in §4 — confirmed the retriever loads it correctly |

---

## 7. Next steps

1. Confirm whether `golden.v1.yaml` or `golden.v2.yaml` should be the one used
   going forward — v2's label fixes were never run through a real eval, so
   there's no scorecard confirming they help.
2. Reconcile the 174 vs 224 document-count discrepancy in §2 before either
   number gets repeated elsewhere.
3. Verify bdren_069–072 against `documents.jsonl` with `--grep`.
4. Decide the hybrid-vs-dense tradeoff as a team, informed by §4.
5. Investigate the `min_score` scale mismatch for hybrid mode before drawing
   further conclusions from hybrid's hallucination number.
6. Chase cases 014/017 — try the URL-path-prepending idea in the chunker.
7. Confirm `context_check.py` and `retrieval_diagnostic.py` still run cleanly.
8. Pick several of the 174 zero-question documents — favoring ones with tables
   or PDFs, since those question shapes are currently unconfirmed in the
   dataset — and write real questions against them.
9. (Tasmia) Split remaining CUET dataset work across the other two Team C
   members using the same authoring workflow (browse → grep-confirm →
   write case → validate).

Full checklist against Team C's definition of done:
[`engine/src/engine/evaluation/README.md`](engine/src/engine/evaluation/README.md) §8.
