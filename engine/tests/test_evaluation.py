import pytest
import yaml

from engine.contracts.evaluation import EvalCase
from engine.contracts.retrieval import RetrievedChunk
from engine.evaluation.dataset import load_dataset, validate_dataset
from engine.evaluation.metrics.answer import citation_precision, contains_expected, refusal_correct
from engine.evaluation.metrics.retrieval import mrr, ndcg_at_k, recall_at_k
from engine.evaluation.runner import EvalConfig, run_evaluation


def test_retrieval_metrics():
    retrieved = ["d3", "d1", "d7"]
    assert recall_at_k(retrieved, ["d1"], 1) == 0.0
    assert recall_at_k(retrieved, ["d1"], 3) == 1.0
    assert recall_at_k(retrieved, ["d1", "d7"], 3) == 1.0
    assert mrr(retrieved, ["d1"]) == pytest.approx(0.5)
    assert mrr(retrieved, ["d9"]) == 0.0
    assert ndcg_at_k(["d1"], ["d1"], 5) == pytest.approx(1.0)
    assert ndcg_at_k(["d9", "d1"], ["d1"], 5) < 1.0


def test_answer_metrics():
    assert contains_expected("Refunds take 5 business days", ["5 business days"]) == 1.0
    assert contains_expected("Refunds are slow", ["5 business days"]) == 0.0
    assert citation_precision(["d1", "d2"], ["d1"]) == pytest.approx(0.5)
    assert citation_precision([], ["d1"]) == 0.0
    assert refusal_correct(refused=True, answerable=False) is True
    assert refusal_correct(refused=True, answerable=True) is False


def test_dataset_requires_unanswerable_cases():
    cases = [EvalCase(case_id="a", question="q", relevant_doc_ids=["d1"])]
    problems = validate_dataset(cases)
    assert any("unanswerable" in p for p in problems)


def test_dataset_rejects_answerable_case_without_ground_truth():
    cases = [
        EvalCase(case_id="a", question="q"),
        EvalCase(case_id="b", question="q2", answerable=False),
    ]
    problems = validate_dataset(cases)
    assert any("relevant_doc_ids" in p for p in problems)


def test_load_dataset_round_trip(tmp_path):
    path = tmp_path / "golden.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "cases": [
                    {"case_id": "a", "question": "q", "relevant_doc_ids": ["d1"]},
                    {"case_id": "b", "question": "unknowable", "answerable": False},
                ]
            }
        )
    )
    cases = load_dataset(path)
    assert [c.case_id for c in cases] == ["a", "b"]
    assert cases[1].answerable is False


class StubRetriever:
    """The eval team builds against this long before the real index exists."""

    def __init__(self, mapping):
        self.mapping = mapping

    def retrieve(self, question, top_k=5):
        return [
            RetrievedChunk(chunk_id=f"{doc}:0", doc_id=doc, text=text, score=0.9,
                           canonical_url=f"https://x.test/{doc}", title=doc)
            for doc, text in self.mapping.get(question, [])
        ][:top_k]


def test_runner_scores_a_mixed_dataset():
    retriever = StubRetriever({
        "refund policy": [("d1", "Annual plans are refunded within 30 days.")],
        "unknowable question": [],
    })
    cases = [
        EvalCase(case_id="ok", question="refund policy", relevant_doc_ids=["d1"],
                 expected_answer_contains=["30 days"]),
        EvalCase(case_id="none", question="unknowable question", answerable=False),
    ]
    report = run_evaluation(cases, retriever, EvalConfig(), dataset_name="t", index_id="i")

    assert report.aggregate["pass_rate"] == 1.0
    assert report.aggregate["hallucination_rate"] == 0.0
    by_id = {r.case_id: r for r in report.results}
    assert by_id["ok"].passed and by_id["ok"].cited_doc_ids == ["d1"]
    assert by_id["none"].refused is True


def test_runner_flags_a_hallucination():
    """A system that answers an unanswerable question must fail the case."""
    retriever = StubRetriever({"unknowable": [("d9", "Some loosely related text about plans.")]})
    cases = [EvalCase(case_id="none", question="unknowable", answerable=False)]
    report = run_evaluation(cases, retriever, EvalConfig(), dataset_name="t", index_id="i")

    assert report.aggregate["hallucination_rate"] == 1.0
    assert report.results[0].passed is False
    assert "unanswerable" in report.results[0].failure_reason
