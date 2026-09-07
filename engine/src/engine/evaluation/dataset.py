"""Load and validate the golden Q/A set.

The dataset is YAML on purpose: it is reviewed in pull requests by people who
are not necessarily programmers, and a bad diff should be obvious.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from engine.contracts.evaluation import EvalCase


def load_dataset(path: str | Path) -> list[EvalCase]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No dataset at {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = payload.get("cases", payload if isinstance(payload, list) else [])
    cases = [EvalCase.from_dict(row) for row in rows]

    problems = validate_dataset(cases)
    if problems:
        raise ValueError("Dataset is invalid:\n  - " + "\n  - ".join(problems))
    return cases


def validate_dataset(cases: list[EvalCase]) -> list[str]:
    problems: list[str] = []
    if not cases:
        return ["dataset contains no cases"]

    seen: set[str] = set()
    for index, case in enumerate(cases):
        label = case.case_id or f"case #{index + 1}"
        if not case.case_id:
            problems.append(f"{label}: case_id is required")
        elif case.case_id in seen:
            problems.append(f"{label}: duplicate case_id")
        seen.add(case.case_id)

        if not case.question.strip():
            problems.append(f"{label}: question is empty")

        # An answerable case with no ground truth cannot be scored.
        if case.answerable and not case.relevant_doc_ids and not case.expected_answer_contains:
            problems.append(
                f"{label}: answerable case needs relevant_doc_ids or expected_answer_contains"
            )
        if not case.answerable and case.relevant_doc_ids:
            problems.append(f"{label}: unanswerable case should not list relevant_doc_ids")

    answerable = sum(1 for c in cases if c.answerable)
    if answerable == len(cases):
        problems.append(
            "every case is answerable — add unanswerable cases, or you are not measuring "
            "whether the system hallucinates"
        )
    return problems
