# Who owns what

Three teams, one pipeline. This is the split, including the parts that are
deliberately *not* yours — most projects like this fail in the gaps between
teams rather than inside them.

Targets: **cuet.ac.bd** and **bdren.net.bd**.

```
   URL ──▶ [ Team A ] ──▶ run directory ──▶ [ Team B ] ──▶ Retriever ──▶ [ Team C ]
            capture         bytes on disk     knowledge      + answers     evaluation
                                                   │                            │
                                                   └────── answer + citations ───┘
                                                              ▲
                                              scorecard ──────┘  feeds back to A and B
```

---

## Team A — Crawler

**Owns** `engine/src/engine/crawler/` and `configs/crawl.*.yaml`
**Deliverable** a run directory per site: `data/sites/<site>/<run>/`

### Responsible for

| | |
|---|---|
| **Reaching the content** | Seeds, scope rules, depth and page budgets. Whether a page that matters actually gets fetched. |
| **Crawling politely** | robots.txt, rate limiting per host, retries and backoff, a real User-Agent, size caps. |
| **Identity** | Canonicalising URLs so one page is one record, and producing stable ids that everything downstream references. |
| **Capture fidelity** | The saved bytes must faithfully represent the live page — encoding, no silent truncation, not an empty JavaScript shell, not a 404 page saved as content. |
| **Linked documents** | Finding PDFs and other linked files, downloading them within their own budget, and recording where each was linked from. |
| **Provenance** | Capturing everything a citation will eventually need. Nothing downstream can invent a source or repair one captured wrong. |
| **Honest reporting** | A manifest that says what was fetched, what was skipped, and what failed. |

### Explicitly not responsible for

- Parsing content out of HTML — no text, no tables, no headings
- Reading PDFs
- Deciding a page is too thin, or that two pages duplicate each other (both need the text, which does not exist at this stage)
- Downloading images

### Depends on

Nothing. They are first, which means their mistakes are also the most expensive
to correct — a gap found in week three means re-crawling.

### Hands over

The path to a run directory. That is the whole interface.

---

## Team B — Knowledge

**Owns** `engine/src/engine/knowledge/`, `configs/extract.*.yaml`, `configs/index.*.yaml`
**Deliverable** `documents.jsonl`, a populated vector store, a `Retriever`, and answers with citations

### Responsible for

| | |
|---|---|
| **Reading the bytes** | Turning saved HTML into clean prose, a title and a breadcrumb, with site chrome removed. Turning PDFs into text. |
| **Tables** | Preserving them as structure rather than loose numbers, and keeping them next to the prose that explains them. |
| **Judging what is content** | Dropping navigation pages; collapsing pages that duplicate each other. |
| **Chunking** | How text is cut for retrieval — the single highest-leverage decision in the pipeline. |
| **Embedding** | Choosing a provider and model, batching, handling rate limits, and keeping index-time and query-time consistent. |
| **Storage** | Getting vectors into Qdrant Cloud along with everything a citation needs, and back out again. |
| **Retrieval and grounding** | Answering only from retrieved context, and refusing when the context does not support an answer. |
| **Citations in the output** | `engine ask` returns references pointing at what the model actually read. |

### Explicitly not responsible for

- Crawling, or any network access during extraction
- Which pages exist in the corpus
- Deciding whether the system is good enough — that is a number, and Team C produces it

### Depends on

Team A's run directory. If content is missing from the saved bytes, that is
Team A's problem; if it is in the bytes but missing from the output, it is theirs.

### Hands over

A `Retriever` object, and `engine ask`.

---

## Team C — Evaluation

**Owns** `engine/src/engine/evaluation/`, `datasets/`, `configs/eval.*.yaml`
**Deliverable** a golden dataset per site, and a scorecard that tells the other teams what to fix

### Responsible for

| | |
|---|---|
| **The golden dataset** | ~60 hand-written cases per site, covering single facts, tables, PDFs, multi-hop questions and vague phrasing. |
| **Unanswerable cases** | Roughly a quarter of them. Without questions the corpus genuinely cannot answer, nobody is measuring hallucination. |
| **Metrics** | Whether retrieval found the right documents, whether the answer was right given them, whether citations are honest, and how often the system invents an answer. |
| **Separating the failures** | A scorecard that says *where* the problem is — retrieval or generation — not just that there is one. |
| **Verifying citations** | They score whether a reference is real and points at what was used. |
| **Feeding back early** | The first real evaluation runs around day 8, not at the end. |

### Weeks one and two — inside the other teams

They have nothing to evaluate for a fortnight, and their own package is the
smallest on purpose. That time belongs to Teams A and B:

- **Mapping the two sites** so Team A can write a sensible crawl config — where the content is, where the PDFs live, what paginates forever, what is a dead archive
- **Data preparation and citations**, in the work rather than downstream of it: given this record, could a reader actually find their way back to the original?
- **Reading output as content**, which is how a leaked cookie banner or a mangled table gets found
- **Handing over questions as requirements**, as they are written

### Explicitly not responsible for

- Fixing the pipeline. They report; A and B fix.
- Deciding which parser, model or chunk size wins — they produce the numbers that settle it.

### Depends on

`documents.jsonl` and a `Retriever`. Neither blocks them: a ten-line fake
retriever and the bundled sample corpus mean the harness and the dataset can
both be built before anything else works.

---

## Shared by all three

**`engine/src/engine/contracts/`** — the schemas every team integrates through.
**Frozen after day 3.** Changing a field afterwards costs everyone a re-run, so
`CODEOWNERS` requires all three teams to approve a change there. Agree them on
day 2.

**`engine/src/engine/cli/`** — thin wiring, shared, all-team review.

**Citations.** The one requirement that runs the length of the pipeline:

| Team | Their part |
|---|---|
| **A** | captures the provenance |
| **B** | carries it into the store and out into the answer |
| **C** | finds out whether it worked |

Settle in week one what a citation must show a reader, and work backwards from
there. Discovering a gap in week three means a re-crawl.

---

## Where responsibility transfers

| Handoff | What crosses | Failure looks like |
|---|---|---|
| **A → B** | a run directory | Content missing from the saved bytes → A. Present in the bytes but missing from `documents.jsonl` → B. |
| **B → C** | a `Retriever` | If it cannot be reopened from an index directory alone, that is B's. |
| **C → A, B** | a scorecard | If it does not say which stage is at fault, it is not finished. |

## Who decides

| Decision | Decided by |
|---|---|
| Anything in `contracts/` | All three, before day 3 |
| What a citation must contain | A and B together, with C in the room, week one |
| Site scope — what is in and out of the crawl | A, informed by C's map of the sites |
| Parser, embedding model, chunk size, refusal threshold | B, settled by C's numbers rather than by argument |
| What counts as a passing answer | C |
| Whether the system is ready | C's scorecard, read by all three |

---

## What every team owes the others

- **Write your decisions down.** Which library, which model, which threshold, and *why*. The reasoning is part of the deliverable.
- **Raise a contract change before day 3**, or live with the schema.
- **Report a problem to the team that owns it** rather than working around it in your own stage.
- **Hand over something that runs.** A README section on what you built, what you left out, and what you know is broken.

---

## Tracking the work

Update the [Daily Tracker](https://docs.google.com/spreadsheets/d/1Z7ob6FwOekNAHNQJ7Top8PGRJwzjMS5_pddJPsGnn7g/edit?usp=sharing) according to your team individually.
