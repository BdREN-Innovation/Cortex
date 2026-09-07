"""Run the golden dataset against any Retriever and produce a RunReport."""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from engine.contracts.evaluation import EvalCase, EvalResult, RunReport
from engine.contracts.retrieval import Retriever
from engine.evaluation.metrics.answer import citation_precision, contains_expected, refusal_correct
from engine.evaluation.metrics.retrieval import mrr, ndcg_at_k, recall_at_k
from engine.knowledge.rag import RagConfig, answer as generate_answer

log = logging.getLogger(__name__)


@dataclass
class EvalConfig:
    top_k: int = 5
    # An answerable case passes when it clears both bars.
    min_answer_score: float = 0.5
    require_citation: bool = True
    rag: RagConfig | None = None

    @classmethod
    def from_dict(cls, payload: dict) -> "EvalConfig":
        rag = RagConfig.from_dict(payload.get("rag", {})) if payload.get("rag") else None
        known = {f for f in cls.__dataclass_fields__ if f != "rag"}
        return cls(rag=rag, **{k: v for k, v in payload.items() if k in known})


def _ordered_doc_ids(chunk_doc_ids: list[str]) -> list[str]:
    """Chunks collapse to documents, keeping first-seen order for rank metrics."""
    seen, ordered = set(), []
    for doc_id in chunk_doc_ids:
        if doc_id not in seen:
            seen.add(doc_id)
            ordered.append(doc_id)
    return ordered


def evaluate_case(case: EvalCase, retriever: Retriever, config: EvalConfig) -> EvalResult:
    rag_config = config.rag or RagConfig(top_k=config.top_k)
    started = time.monotonic()

    retrieved = retriever.retrieve(case.question, top_k=config.top_k)
    retrieved_doc_ids = _ordered_doc_ids([c.doc_id for c in retrieved])

    produced = generate_answer(case.question, retriever, rag_config)
    cited_doc_ids = _ordered_doc_ids([c.doc_id for c in produced.citations])

    metrics: dict = {
        "recall@1": recall_at_k(retrieved_doc_ids, case.relevant_doc_ids, 1),
        f"recall@{config.top_k}": recall_at_k(retrieved_doc_ids, case.relevant_doc_ids, config.top_k),
        "mrr": mrr(retrieved_doc_ids, case.relevant_doc_ids),
        f"ndcg@{config.top_k}": ndcg_at_k(retrieved_doc_ids, case.relevant_doc_ids, config.top_k),
        "answer_match": contains_expected(produced.text, case.expected_answer_contains),
        "citation_precision": citation_precision(cited_doc_ids, case.relevant_doc_ids),
        "refusal_correct": float(refusal_correct(produced.refused, case.answerable)),
    }

    if not case.answerable:
        # The only thing that matters here is that the system declined.
        passed = produced.refused
        reason = "" if passed else "answered an unanswerable question"
    else:
        passed = True
        reason = ""
        if produced.refused:
            passed, reason = False, "refused an answerable question"
        elif metrics["answer_match"] < config.min_answer_score:
            passed = False
            reason = f"answer_match {metrics['answer_match']:.2f} < {config.min_answer_score}"
        elif config.require_citation and not cited_doc_ids:
            passed, reason = False, "no citations"
        elif case.relevant_doc_ids and metrics[f"recall@{config.top_k}"] == 0.0:
            passed, reason = False, "no relevant document retrieved"

    return EvalResult(
        case_id=case.case_id,
        question=case.question,
        answerable=case.answerable,
        answer_text=produced.text,
        refused=produced.refused,
        retrieved_doc_ids=retrieved_doc_ids,
        cited_doc_ids=cited_doc_ids,
        metrics=metrics,
        passed=passed,
        failure_reason=reason,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def aggregate(results: list[EvalResult]) -> dict:
    if not results:
        return {}

    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]

    def mean(values: list[float]) -> float:
        return round(statistics.fmean(values), 4) if values else 0.0

    keys: set[str] = set()
    for result in results:
        keys.update(result.metrics)

    summary = {
        "pass_rate": mean([float(r.passed) for r in results]),
        "pass_rate_answerable": mean([float(r.passed) for r in answerable]),
        "pass_rate_unanswerable": mean([float(r.passed) for r in unanswerable]),
        "hallucination_rate": mean([float(not r.refused) for r in unanswerable]),
        "latency_ms_p50": round(statistics.median([r.latency_ms for r in results]), 1),
        "cases": len(results),
        "cases_answerable": len(answerable),
        "cases_unanswerable": len(unanswerable),
    }
    # Retrieval metrics only mean something on cases with ground truth.
    for key in sorted(keys):
        summary[key] = mean([r.metrics.get(key, 0.0) for r in answerable]) if answerable else 0.0
    return summary


def run_evaluation(
    cases: list[EvalCase],
    retriever: Retriever,
    config: EvalConfig | None = None,
    dataset_name: str = "",
    index_id: str = "",
) -> RunReport:
    config = config or EvalConfig()
    started_at = datetime.now(timezone.utc)

    results = []
    for position, case in enumerate(cases, start=1):
        log.info("[%s/%s] %s", position, len(cases), case.case_id)
        results.append(evaluate_case(case, retriever, config))

    return RunReport(
        run_id=started_at.strftime("%Y%m%dT%H%M%SZ"),
        dataset=dataset_name,
        index_id=index_id,
        started_at=started_at.isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        case_count=len(cases),
        aggregate=aggregate(results),
        results=results,
        config={
            "top_k": config.top_k,
            "min_answer_score": config.min_answer_score,
            "require_citation": config.require_citation,
            "rag_provider": (config.rag or RagConfig()).provider,
            "rag_model": (config.rag or RagConfig()).model,
        },
    )
