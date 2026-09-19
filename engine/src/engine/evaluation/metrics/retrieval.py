"""Did we find the right documents?

Retrieval metrics answer a different question from answer metrics: not "was the
reply good" but "were the right documents in front of the model at all". When a
system answers badly, these tell you whether to blame retrieval or generation —
which is the single most useful diagnostic Team C provides.

TEAM C OWNS THIS FILE. Pure functions, no dependencies, easy to test — a good
place to start on day one.


Decisions you own
-----------------
* Which metrics? There are several standard ones for ranked retrieval and they
  answer different questions — "did we find it at all" is not the same as "did
  we rank it first". Pick the ones that would change what Team B does next.
* What is the right value when there is nothing relevant to find? An
  unanswerable case has not failed retrieval, but a naive implementation scores
  it zero and drags your averages down. This is a judgement call — make it
  deliberately and write it down.
* Are all relevant documents equally relevant, or do you need graded relevance?
  Binary is simpler and probably enough here. Decide, do not drift.
"""

from __future__ import annotations

import math


def recall_at_k(retrieved_doc_ids: list[str], relevant_doc_ids: list[str], k: int) -> float:
    """What fraction of the relevant documents appear in the top k?

    Return 1.0 when there are no relevant documents to find — an unanswerable
    case has not failed retrieval. Deciding this deliberately matters: the
    alternative (0.0) drags the average down for cases that were never
    supposed to retrieve anything.
    """
    if not relevant_doc_ids:
        return 1.0

    top_k = retrieved_doc_ids[:k]
    relevant_set = set(relevant_doc_ids)
    found = sum(1 for doc_id in top_k if doc_id in relevant_set)
    return found / len(relevant_set)


def mrr(retrieved_doc_ids: list[str], relevant_doc_ids: list[str]) -> float:
    """Mean reciprocal rank: 1/rank of the FIRST relevant document.

    Rank 1 -> 1.0, rank 2 -> 0.5, rank 5 -> 0.2, nothing relevant -> 0.0.
    Ranks are 1-based. This is the metric that notices "the right answer was
    there, but at position 9" — which recall@5 reports as a flat failure.
    """
    if not relevant_doc_ids:
        return 0.0

    relevant_set = set(relevant_doc_ids)
    for rank, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_doc_ids: list[str], relevant_doc_ids: list[str], k: int) -> float:
    """Normalised discounted cumulative gain: rank-aware, normalised to [0, 1].

    Binary relevance is fine here. DCG sums 1/log2(rank+1) over the relevant
    hits; divide by the ideal DCG (the same sum if every relevant document sat
    at the top). Return 0.0, not NaN, when the ideal is zero.
    """
    if not relevant_doc_ids:
        return 0.0

    relevant_set = set(relevant_doc_ids)
    top_k = retrieved_doc_ids[:k]

    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc_id in enumerate(top_k, start=1)
        if doc_id in relevant_set
    )

    ideal_hits = min(len(relevant_set), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))

    if ideal_dcg == 0.0:
        return 0.0
    return dcg / ideal_dcg
