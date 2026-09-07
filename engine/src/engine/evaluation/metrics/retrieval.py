"""Retrieval quality. These are the numbers to fix first: an answer can never be
better than the passages it was given."""

from __future__ import annotations

import math


def recall_at_k(retrieved_doc_ids: list[str], relevant_doc_ids: list[str], k: int) -> float:
    """Share of the relevant documents that appear in the top k."""
    if not relevant_doc_ids:
        return 0.0
    top = set(retrieved_doc_ids[:k])
    hits = sum(1 for doc_id in set(relevant_doc_ids) if doc_id in top)
    return hits / len(set(relevant_doc_ids))


def mrr(retrieved_doc_ids: list[str], relevant_doc_ids: list[str]) -> float:
    """Reciprocal rank of the first relevant document. Rewards ranking it first."""
    relevant = set(relevant_doc_ids)
    for position, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in relevant:
            return 1.0 / position
    return 0.0


def ndcg_at_k(retrieved_doc_ids: list[str], relevant_doc_ids: list[str], k: int) -> float:
    """Rank-weighted gain, normalised against a perfect ordering."""
    relevant = set(relevant_doc_ids)
    if not relevant:
        return 0.0
    gain = sum(
        1.0 / math.log2(position + 1)
        for position, doc_id in enumerate(retrieved_doc_ids[:k], start=1)
        if doc_id in relevant
    )
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return gain / ideal if ideal else 0.0
