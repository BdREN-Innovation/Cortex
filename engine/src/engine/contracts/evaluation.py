"""The golden dataset and the scorecard it produces."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    """One question in the baseline dataset.

    `answerable=False` cases are the point of the exercise as much as the rest:
    a system that invents an answer when the corpus does not contain one is
    worse than one that says so.
    """

    case_id: str
    question: str
    answerable: bool = True
    # Documents that genuinely contain the answer — drives recall@k / MRR.
    relevant_doc_ids: list[str] = field(default_factory=list)
    # Strings a correct answer is expected to contain (case-insensitive).
    expected_answer_contains: list[str] = field(default_factory=list)
    expected_answer: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict) -> "EvalCase":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class EvalResult:
    """How the system did on one case."""

    case_id: str
    question: str
    answerable: bool
    answer_text: str = ""
    refused: bool = False
    retrieved_doc_ids: list[str] = field(default_factory=list)
    cited_doc_ids: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    passed: bool = False
    failure_reason: str = ""
    latency_ms: int = 0


@dataclass
class RunReport:
    """The scorecard. Same dataset + same config should give the same numbers."""

    run_id: str
    dataset: str
    index_id: str
    started_at: str
    finished_at: str
    case_count: int
    aggregate: dict = field(default_factory=dict)
    results: list[EvalResult] = field(default_factory=list)
    config: dict = field(default_factory=dict)
