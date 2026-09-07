"""Answer quality without an LLM judge.

These are deliberately deterministic: the same run gives the same score, which
is what makes a baseline useful for comparing two configurations. An optional
LLM judge can be layered on later for nuance, but it should never replace these.
"""

from __future__ import annotations


def contains_expected(answer_text: str, expected: list[str]) -> float:
    """Share of required strings present in the answer (case-insensitive)."""
    if not expected:
        return 1.0
    haystack = answer_text.lower()
    hits = sum(1 for needle in expected if needle.lower() in haystack)
    return hits / len(expected)


def citation_precision(cited_doc_ids: list[str], relevant_doc_ids: list[str]) -> float:
    """Share of citations that point at genuinely relevant documents.

    This is the anti-hallucination metric: an answer can contain the right words
    while citing the wrong page, and that is still a defect.
    """
    if not cited_doc_ids:
        return 0.0
    relevant = set(relevant_doc_ids)
    if not relevant:
        return 0.0
    hits = sum(1 for doc_id in cited_doc_ids if doc_id in relevant)
    return hits / len(cited_doc_ids)


def refusal_correct(refused: bool, answerable: bool) -> bool:
    """Refusing an unanswerable question is a pass; refusing an answerable one is not."""
    return refused != answerable
