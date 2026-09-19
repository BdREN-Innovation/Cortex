"""Score every case, aggregate.

TEAM C OWNS THIS FILE.

Runs the full pipeline (retrieve -> answer -> score) over a dataset and
produces the per-case results plus one aggregate dict. It is the only file
that ties `metrics/` to the rest of the system, so it is written last.

Decisions you own
-----------------
* How is `passed` decided? A single boolean has to combine retrieval quality,
  answer quality and refusal correctness into one verdict — decide the
  threshold and write it down, because people will build on it.
* What is the right citation_precision for an unanswerable case with no
  citations? contains_expected and citation_precision are pure functions that
  do not know case type; this file is where that context lives.
* Do you fail fast or keep going on an exception? One bad case should not
  lose the other fifty-nine results.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from engine.contracts.evaluation import EvalCase, EvalResult, RunReport
from engine.contracts.retrieval import Retriever
from engine.evaluation.metrics.answer import (
    citation_precision,
    contains_expected,
    refusal_correct,
)
from engine.evaluation.metrics.retrieval import mrr, ndcg_at_k, recall_at_k
from engine.knowledge.rag import RagConfig, answer as generate_answer

# A case "passes" when the system got the right documents, said something
# correct about them (or correctly refused), and did not hallucinate a
# citation. Any one of these failing means the case failed — there is no
# partial credit here, because partial credit here would let a badly-cited
# hallucination masquerade as an 80% success.
_RECALL_PASS_THRESHOLD = 0.5
_ANSWER_PASS_THRESHOLD = 0.5


def score_case(case: EvalCase, retriever: Retriever, config: RagConfig | None = None) -> EvalResult:
    """Retrieve, answer, and score ONE case. Never raises for a scoring
    failure — an exception here is caught and turned into a failed result so
    that one bad case does not lose the other fifty-nine.
    """
    start = time.monotonic()
    try:
        result_answer = generate_answer(case.question, retriever, config)
        latency_ms = int((time.monotonic() - start) * 1000)

        retrieved_doc_ids = list(
            dict.fromkeys(
                # retrieved_chunk_ids on Answer are chunk ids; for doc-level
                # retrieval metrics we need doc ids, which live on the
                # citations when present, else fall back to chunk ids.
                c.doc_id for c in result_answer.citations
            )
        ) or result_answer.retrieved_chunk_ids
        cited_doc_ids = list(dict.fromkeys(c.doc_id for c in result_answer.citations))

        recall = recall_at_k(retrieved_doc_ids, case.relevant_doc_ids, k=5)
        rank_score = mrr(retrieved_doc_ids, case.relevant_doc_ids)
        ndcg = ndcg_at_k(retrieved_doc_ids, case.relevant_doc_ids, k=5)

        answer_score = contains_expected(result_answer.text, case.expected_answer_contains)

        if case.answerable:
            cite_score = citation_precision(cited_doc_ids, case.relevant_doc_ids)
        else:
            # No ground truth to cite; citing nothing is correct here.
            cite_score = 1.0 if not cited_doc_ids else 0.0

        refusal_ok = refusal_correct(result_answer.refused, case.answerable)

        metrics = {
            "recall_at_5": recall,
            "mrr": rank_score,
            "ndcg_at_5": ndcg,
            "answer_score": answer_score,
            "citation_precision": cite_score,
            "refusal_correct": refusal_ok,
        }

        if case.answerable:
            passed = (
                refusal_ok
                and recall >= _RECALL_PASS_THRESHOLD
                and answer_score >= _ANSWER_PASS_THRESHOLD
            )
        else:
            # For an unanswerable case, the only thing that matters is that
            # the system refused. A hallucinated answer here is the failure
            # this whole harness exists to catch.
            passed = refusal_ok

        failure_reason = "" if passed else _explain_failure(case, refusal_ok, recall, answer_score)

        return EvalResult(
            case_id=case.case_id,
            question=case.question,
            answerable=case.answerable,
            answer_text=result_answer.text,
            refused=result_answer.refused,
            retrieved_doc_ids=retrieved_doc_ids,
            cited_doc_ids=cited_doc_ids,
            metrics=metrics,
            passed=passed,
            failure_reason=failure_reason,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - one bad case must not kill the run
        latency_ms = int((time.monotonic() - start) * 1000)
        return EvalResult(
            case_id=case.case_id,
            question=case.question,
            answerable=case.answerable,
            answer_text="",
            refused=False,
            metrics={},
            passed=False,
            failure_reason=f"exception during scoring: {exc!r}",
            latency_ms=latency_ms,
        )


def _explain_failure(case: EvalCase, refusal_ok: bool, recall: float, answer_score: float) -> str:
    if not refusal_ok:
        if case.answerable:
            return "system refused a question it should have answered"
        return "system answered a question it should have refused (hallucination)"
    if recall < _RECALL_PASS_THRESHOLD:
        return f"retrieval missed relevant documents (recall={recall:.2f})"
    if answer_score < _ANSWER_PASS_THRESHOLD:
        return f"answer text did not contain expected facts (score={answer_score:.2f})"
    return "failed"


def run_eval(
    cases: list[EvalCase],
    retriever: Retriever,
    config: RagConfig | None = None,
    *,
    run_id: str = "",
    dataset_name: str = "",
    index_id: str = "",
) -> RunReport:
    """Score every case and aggregate. This is the entry point `engine eval` calls."""
    started_at = datetime.now(timezone.utc).isoformat()

    results = [score_case(case, retriever, config) for case in cases]

    aggregate = aggregate_results(results)

    finished_at = datetime.now(timezone.utc).isoformat()

    return RunReport(
        run_id=run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        dataset=dataset_name,
        index_id=index_id,
        started_at=started_at,
        finished_at=finished_at,
        case_count=len(cases),
        aggregate=aggregate,
        results=results,
        config=dict(vars(config)) if config is not None else {},
    )


def aggregate_results(results: list[EvalResult]) -> dict:
    """Roll per-case results into report-level numbers.

    Split answerable and unanswerable throughout — a single blended pass rate
    hides the split that actually matters: a system can look great by
    answering everything and refusing nothing.
    """
    if not results:
        return {
            "pass_rate": 0.0,
            "pass_rate_answerable": 0.0,
            "pass_rate_unanswerable": 0.0,
            "mean_recall_at_5": 0.0,
            "mean_mrr": 0.0,
            "mean_ndcg_at_5": 0.0,
            "mean_answer_score": 0.0,
            "mean_citation_precision": 0.0,
            "hallucination_rate": 0.0,
            "case_count": 0,
        }

    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]

    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _pass_rate(subset: list[EvalResult]) -> float:
        return _mean([1.0 if r.passed else 0.0 for r in subset])

    # Hallucination: an unanswerable case where the system answered anyway
    # (did not refuse). This is the single most important number in the
    # report — it is what decides whether the system can be trusted.
    hallucinated = [r for r in unanswerable if not r.refused]
    hallucination_rate = (
        len(hallucinated) / len(unanswerable) if unanswerable else 0.0
    )

    return {
        "case_count": len(results),
        "pass_rate": _pass_rate(results),
        "pass_rate_answerable": _pass_rate(answerable),
        "pass_rate_unanswerable": _pass_rate(unanswerable),
        "mean_recall_at_5": _mean([r.metrics.get("recall_at_5", 0.0) for r in answerable]),
        "mean_mrr": _mean([r.metrics.get("mrr", 0.0) for r in answerable]),
        "mean_ndcg_at_5": _mean([r.metrics.get("ndcg_at_5", 0.0) for r in answerable]),
        "mean_answer_score": _mean([r.metrics.get("answer_score", 0.0) for r in answerable]),
        "mean_citation_precision": _mean(
            [r.metrics.get("citation_precision", 0.0) for r in results]
        ),
        "hallucination_rate": hallucination_rate,
    }
