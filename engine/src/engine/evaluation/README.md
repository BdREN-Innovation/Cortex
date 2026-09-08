# Team C — Evaluation

**You build this.** Every file in this folder is a stub that raises
`NotImplementedError`. The signature and docstring of each function are
the specification; the code is yours to write.

```bash
uv run python scripts/progress.py --detail   # what is left in your files
```

Your 7 tests are the smallest share, and that is deliberate: **the code is not
the job.** The golden dataset is. Writing 60 good questions by hand is harder,
slower and worth more than any function in this folder.

---

## 1. What you own

You decide whether the system actually works. Without you, Teams A and B are
guessing — a RAG pipeline always *looks* impressive on the three questions its
author happened to try.

You produce two things:

1. **`datasets/<site>/golden.v1.yaml`** — questions with known-correct answers.
   This is the deliverable that outlives the project.
2. **A scorecard** that tells the other teams *what to fix*, not just how they did.

---

## 2. Build order

| # | File | What it does | Tests |
|---|---|---|---|
| 1 | `metrics/retrieval.py` | recall@k, MRR, nDCG | 1 |
| 2 | `metrics/answer.py` | answer match, citation precision, refusal | 1 |
| 3 | `dataset.py` | Load and validate the golden set | 3 |
| 4 | `runner.py` | Score every case, aggregate | 2 |
| 5 | `report.py` | Render a scorecard people will read | — |

**Start with the metrics.** They are pure functions with no dependencies —
you can finish them on day one while Teams A and B are still fetching their
first page. Then write dataset questions while waiting for a real index.

---

## 3. You are not blocked. Ever.

This is the thing to understand on day one: **you do not need Team B's retriever
to start.** The `Retriever` Protocol in `contracts/retrieval.py` is the only
thing you code against, and it is three lines:

```python
class Retriever(Protocol):
    def retrieve(self, question: str, top_k: int = 5) -> list[RetrievedChunk]: ...
```

Write a fake one in ten lines and build your entire harness against it:

```python
class FakeRetriever:
    def __init__(self, chunks): self.chunks = chunks
    def retrieve(self, question, top_k=5):
        return [c for c in self.chunks if question.split()[0].lower() in c.text.lower()][:top_k]
```

When Team B's real retriever lands, you swap the object in and change
nothing else — that is what coding against a Protocol buys you.

---

## 4. Building the dataset from the cleaned data

This is the real work. Budget most of your two weeks for it.

Your source is **`documents.jsonl`** — Team B's cleaned output, not the live
site. That matters: you must write questions against the text the system will
actually search. A fact that exists on the website but got stripped during
extraction is not answerable by this system, and a question about it is testing
Team B's extractor, not the RAG pipeline. That is a finding worth reporting —
just do not silently mark it as a failed answer.

### Day 1: you are not waiting for anyone

A sample corpus ships with the repo, so you can start before Teams A and B have
finished anything:

```bash
uv run python scripts/browse_documents.py datasets/acme/documents.sample.jsonl
```

```
  doc_id             type   chars  title
  18a4abaa5dac2d1c   page     211  Acme Cloud
  8c20505cbc149242   page     394  Billing - Acme Cloud
  bc89702913b72ba7   page     349  Plan limits - Acme Cloud
  7c9449099579549c   page     329  Refunds - Acme Cloud
  ec1b44c0c4ca8397   page     397  Plans - Acme Cloud
  75f8203414c038e9   pdf      177  Acme Refund Policy
```

`datasets/acme/golden.v1.yaml` is a worked example over that corpus, annotated
with the reasoning behind every case. Read it before writing your own.

### The authoring loop

**1. Read a document in full.** Do not write questions from memory or from the
website — write them from the extracted text.

```bash
uv run python scripts/browse_documents.py <corpus> --show 7c94
```

It prints the document with its `doc_id` and breadcrumb, then a ready-to-paste
YAML skeleton. Copy it, write the question, fill in the expected strings.

**2. Find which document states a fact.**

```bash
uv run python scripts/browse_documents.py <corpus> --grep "business days"
```

Use this to fill `relevant_doc_ids` accurately. If two documents match, you may
have found a **conflicting source** — a genuinely valuable case (see shape 6 in
the worked example).

**3. Confirm a question is unanswerable before marking it so.**

```bash
uv run python scripts/browse_documents.py <corpus> --grep "uptime SLA"
#   no match — good candidate for an `answerable: false` case
```

Never guess at this. An `answerable: false` case that the corpus *does* answer
penalises a correct system, and you will spend a day chasing a bug that is in
your dataset.

**4. Check coverage as you go.**

```bash
uv run python scripts/browse_documents.py <corpus> --coverage datasets/<site>/golden.v1.yaml
```

```
  16 cases: 11 answerable, 5 unanswerable
  unanswerable share: 31%  (good)
  18a4abaa5dac2d1c       0  Acme Cloud  <-- no questions
```

A document nobody asks about is a document you are not testing.

### Cover the shapes, not just the topics

Nine shapes, each catching a different failure. The worked example has one of
each — aim for several of each in a real dataset.

| # | Shape | Catches |
|---|---|---|
| 1 | Single fact from one page | baseline retrieval |
| 2 | Negative fact ("can I refund monthly?" → no) | systems that flip a "no" into a "yes" |
| 3 | **From a table** | whether tables survived extraction as grids |
| 4 | **From a PDF** | whether PDFs were parsed at all — a silent failure |
| 5 | Multi-hop, needs two documents | whether chunks combine, or only the top one is used |
| 6 | Conflicting sources | whether citations let a human see which source was used |
| 7 | Vague wording ("how much for the pro one") | robustness to real user input |
| 8 | **Unanswerable** | **hallucination** |
| 9 | Near-miss (adjacent topic, no answer) | over-eager retrieval |

Shapes 3 and 4 are how you tell Team B their parser choice is wrong. Shape 8 is
how you tell them their `min_score` is wrong. That specificity is what makes a
scorecard actionable.

### Rules that make a dataset useful

**About a quarter must be `answerable: false`.** This is the rule people skip
and the one that matters most. Without questions the corpus genuinely cannot
answer, you are only measuring recall — you will never detect hallucination, and
hallucination is what destroys trust in a RAG system.

Good unanswerable questions are **plausible**: right topic, the site's own
vocabulary, no answer present. "What is the capital of France" tests nothing.
"What discount do I get for paying annually?" on a site that discusses both
billing and annual plans is a genuine trap — retrieval will return
confident-looking chunks and the system must refuse anyway.

**`expected_answer_contains` holds short, factual, hard-to-paraphrase strings.**
`"30 days"`, `"$29"`, `"429"`. Not whole sentences — the matcher is
substring-based, so a correct paraphrase would fail.

**Every answerable case needs `relevant_doc_ids`.** A case with no ground truth
cannot be scored, so it is worse than no case: it inflates the denominator and
tells you nothing. `validate_dataset()` enforces this.

**Version the file.** `golden.v1.yaml`, then `v2`. A score is meaningless
without knowing which dataset produced it. Never edit history — old scorecards
must stay comparable.

### One caution about doc_ids

`doc_id` is a hash of the canonical URL. It is stable as long as the URL is —
but if Team A changes `canonicalize()` or the seeds, every id shifts and your
`relevant_doc_ids` all break. `--coverage` catches this:

```
  WARNING: 4 relevant_doc_ids are not in this corpus
```

Do not fix that by hand-editing ids one at a time. Re-run `--coverage` against
the new corpus, and if the whole dataset broke, ask Team A what changed —
after the day-3 contract freeze it should not be happening.

### Targets

**~20 cases by day 3, ~60 by day 8.** Twenty is enough to start finding bugs;
sixty is enough for the numbers to mean something. Write them against the sample
corpus first, then re-point at real data when it lands.

## 5. The decisions are yours

Nothing is preinstalled beyond what the scaffold uses. No library is
prescribed — and for this package you may genuinely need almost none. Metrics
you wrote yourself are metrics you can defend when someone disputes a score,
and you will be disputed.

Add whatever you do want with `uv add`, and commit `pyproject.toml` and
`uv.lock` together.

Some questions worth working through before you write the first metric:

* **Substring matching or something smarter?** Checking whether an answer
  contains "30 days" is cheap, deterministic and runs anywhere. It also cannot
  tell a correct paraphrase from a wrong answer. Where does that break down for
  your questions, and what would you do about it?
* **An LLM as judge?** It handles paraphrase. It also costs money per run, is
  non-deterministic, and cannot be reproduced later. If you add one, is it
  instead of the cheap metric or alongside it?
* **Which retrieval metrics?** There are several standard ones and they answer
  different questions — "did we find it at all" is not "did we rank it first".
  Pick the ones that would change what Team B does next.
* **What is the right answer for an edge case?** Recall when there is nothing
  relevant to find. Citation precision when nothing was cited. These are
  judgement calls; make them deliberately and write them down, because your
  averages depend on them.

There are off-the-shelf RAG evaluation frameworks. Read about them — the ideas
in them are good — but think hard before adopting one. A metric you cannot
explain is a metric the other teams will argue with instead of act on.

---

## 6. Making the report worth reading

Your audience is Teams A and B, and your purpose is to make them **change
something**. A wall of numbers gets skimmed.

Report these separately, never as one number:

| What it answers | Why it earns its place |
|---|---|
| Were the right documents even retrieved? | Separates a retrieval problem from a generation one |
| Given the right documents, was the answer right? | The other half of that split |
| Did it cite what it actually used? | Catches an answer padded with sources it never read |
| **How often did it answer something unanswerable?** | **The number that decides whether this is trustworthy** |
| Pass rate, split answerable / unanswerable | The headline, honestly stated |

Name them whatever you like — nothing downstream hardcodes your metric names,
including the CLI, which prints whatever `aggregate` you produce and gates CI
on whichever key you point `--gate-metric` at.

The split matters: a system can score 80% overall by answering everything well
and refusing nothing — which is a system you cannot ship.

**Retrieval vs generation is the most useful thing you tell Team B.** High
recall with a low answer score means the prompt is wrong. Low recall means
chunking or embeddings are wrong. Those are different files and different people.

Then the part that earns its keep: **a table of failing cases** showing the
question, what was expected, what came back, and which documents were retrieved.
That table is what actually gets fixed.

---

## 7. Syncing with the other teams

Citations are a three-team concern: Team A captures the provenance, Team B
carries it into the store and out into the answer, and **you are the one who
finds out whether it actually worked.** Your dataset is what turns "we think
citations work" into a number. Score them early — a missing reference
discovered in week one is a config change, and in week three it is a re-crawl.

| You need | From | How |
|---|---|---|
| `doc_id`s for `relevant_doc_ids` | Team A | Read `pages.jsonl` — `page_id` becomes `doc_id` |
| A `Retriever` | Team B | `load_retriever(index_dir)`; until then, use a fake |
| A refusal to detect | Team B | `Answer.refused` and the `REFUSAL` constant in `rag.py` |

`EvalCase`, `EvalResult` and `RunReport` live in `contracts/` and are **frozen
after day 3**.

**Feed failures back early and often.** A scorecard delivered on day 14 is a
post-mortem. One delivered on day 8 changes what the other teams build. Run the
eval the day Team B's first index exists, even if your dataset only has twenty
cases and the numbers are bad — *especially* then.

---

## 8. Definition of done

- [ ] ~60 cases per site, with ~25% `answerable: false`
- [ ] Every case written against `documents.jsonl`, not from the live website
- [ ] `--coverage` shows no document with zero questions and no unknown doc_ids
- [ ] Every answerable case has `relevant_doc_ids` and `expected_answer_contains`
- [ ] Coverage of every shape in the §4 table, including table and PDF questions
- [ ] `engine eval` runs against Team B's real index and writes a report
- [ ] The report separates retrieval from generation, and reports hallucination rate
- [ ] You delivered at least one mid-project scorecard that changed what someone built
- [ ] A short written verdict: what this system is and is not ready for

---

Config reference: [configs/README.md](../../../configs/README.md) — how the four
config types map to the pipeline stages, plus a worked end-to-end example.
