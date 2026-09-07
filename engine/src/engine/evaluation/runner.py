"""Run the dataset against a retriever and score every case.

This is where Team C's work turns into a number the other two teams can act on.
A scorecard that says "68%" is useless on its own; one that says "retrieval
recall 0.91, answer score 0.62, hallucination rate 0.18" tells Team B exactly
where to look.

TEAM C OWNS THIS FILE.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from engine.contracts.evaluation import EvalCase, EvalResult, RunReport
from engine.contracts.retrieval import Retriever
from engine.knowledge.rag import RagConfig

log = logging.getLogger(__name__)


@dataclass
class EvalConfig:
    top_k: int = 5
    # An answer scoring below this counts as a failure.
    min_answer_score: float = 0.5
    require_citation: bool = True
    rag: RagConfig | None = None

    @classmethod
    def from_dict(cls, payload: dict) -> "EvalConfig":
        raise NotImplementedError


def evaluate_case(case: EvalCase, retriever: Retriever, config: EvalConfig) -> EvalResult:
    """Score one case.

    Ask the question, then compute every metric for it and record WHY it
    passed or failed in `failure_reason`. That string is what makes a report
    actionable — "retrieved nothing" and "answered but did not cite" send Team
    B to completely different files.

    Pass criteria differ by case type, and this is the part to get right:

      answerable   retrieval found the relevant docs, the answer contains what
                   it should, it did not refuse, and (if require_citation) it
                   cited something relevant.

      unanswerable it REFUSED. Nothing else counts. An unanswerable case that
                   produces a fluent, well-cited, entirely invented answer is
                   the worst outcome the system can produce, and it must score
                   zero here.

    Never let one exploding case kill the run — catch, record the failure, and
    carry on to the next.
    """
    raise NotImplementedError


def aggregate(results: list[EvalResult]) -> dict:
    """Roll individual results into headline numbers.

    Report at minimum:
      pass_rate, and pass_rate split by answerable vs unanswerable
      mean retrieval metrics (recall@k, mrr, ndcg)
      mean answer score
      hallucination_rate — unanswerable cases that were answered anyway

    The overall pass rate alone hides the thing you most need to see: a system
    can score 80% by answering everything well and refusing nothing.
    """
    raise NotImplementedError


def run_evaluation(
    cases: list[EvalCase],
    retriever: Retriever,
    config: EvalConfig | None = None,
    dataset_name: str = "",
    index_id: str = "",
) -> RunReport:
    """Score every case and return a RunReport.

    Record `index_id` and `dataset_name` in the report. A score is meaningless
    without knowing which index and which dataset version produced it, and on
    day 12 someone WILL ask why yesterday's number was different.
    """
    raise NotImplementedError
