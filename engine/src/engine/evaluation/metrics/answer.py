"""Was the answer any good, and was it honest?

TEAM C OWNS THIS FILE.

"""

from __future__ import annotations


def contains_expected(answer_text: str, expected: list[str]) -> float:
    """Fraction of the expected strings present in the answer.

    Deliberately crude: substring matching, case-insensitive. It is cheap,
    deterministic and needs no API key, which means it can run on every commit.

    Know its limits and write them in your report: it cannot tell a correct
    paraphrase from a wrong answer, so `expected_answer_contains` should hold
    short, factual, hard-to-paraphrase strings ("5 business days", "$29") and
    not whole sentences. If you later want semantic scoring, an LLM judge is
    the usual next step — but get this working and calibrated first.
    """
    raise NotImplementedError


def citation_precision(cited_doc_ids: list[str], relevant_doc_ids: list[str]) -> float:
    """Of the documents cited, what fraction were actually relevant?

    This is the anti-hallucination metric. A system that cites four documents
    to answer a one-document question is padding, and padding is how a wrong
    answer gets made to look well-sourced.

    Decide and document what "no citations" means: for an answerable case it is
    a failure, for an unanswerable one it is correct.
    """
    raise NotImplementedError


def refusal_correct(refused: bool, answerable: bool) -> bool:
    """Did the system refuse exactly when it should have?

    True when it refused an unanswerable question, or answered an answerable
    one. The two failure modes are NOT equally bad and your report should
    separate them: refusing a real question is annoying, while confidently
    answering an unanswerable one is the failure that loses trust in the whole
    system.
    """
    raise NotImplementedError
