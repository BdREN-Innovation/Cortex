"""The golden dataset: questions with known-correct answers.

This file loads and validates it. Writing the dataset itself is the harder and
more valuable half of Team C's job — see datasets/ and the team README.

TEAM C OWNS THIS FILE.

Decisions you own
-----------------
* What file format? It has to be comfortable to hand-write sixty times and
  reviewable in a pull request.
* What makes a case invalid? Be strict — a case that cannot be scored is worse
  than no case, because it inflates the denominator and tells you nothing.
* Do you report the first problem or all of them? Someone fixing a 60-case
  dataset should get one report, not sixty round trips.

Format decision: YAML. It is comfortable to hand-write, diffs cleanly in a
pull request, and supports comments — which matters when a case needs a note
explaining why it is a good "answerable: false" trap.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from engine.contracts.evaluation import EvalCase


def load_dataset(path: str | Path) -> list[EvalCase]:
    """Read `datasets/<site>/golden.v1.yaml` into EvalCases.

    Validate on load and raise with ALL the problems listed, not just the
    first. Someone fixing a 60-case dataset should get one report, not sixty
    round trips.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}

    raw_cases = payload.get("cases", payload if isinstance(payload, list) else [])
    cases = [EvalCase.from_dict(raw) for raw in raw_cases]

    problems = validate_dataset(cases)
    if problems:
        joined = "\n".join(f"  - {p}" for p in problems)
        raise ValueError(
            f"{path} failed validation ({len(problems)} problem(s)):\n{joined}"
        )

    return cases


def validate_dataset(cases: list[EvalCase]) -> list[str]:
    """Return a list of problems; empty means the dataset is sound.

    Enforce at least:

      * `case_id` present and UNIQUE. Duplicate ids silently overwrite results.
      * An answerable case must have ground truth — `relevant_doc_ids` and
        something in `expected_answer_contains`. A case with no ground truth
        cannot be scored, so it is worse than no case: it inflates the
        denominator and tells you nothing.
      * The dataset must contain SOME unanswerable cases. This is the rule
        people skip, and it is the one that matters most. Without questions the
        corpus genuinely cannot answer, you are only measuring recall and you
        will never detect hallucination. Aim for roughly a quarter.
    """
    problems: list[str] = []

    seen_ids: dict[str, int] = {}
    for i, case in enumerate(cases):
        if not case.case_id:
            problems.append(f"case at index {i}: missing case_id")
        else:
            if case.case_id in seen_ids:
                problems.append(
                    f"case_id '{case.case_id}' is duplicated "
                    f"(indices {seen_ids[case.case_id]} and {i})"
                )
            else:
                seen_ids[case.case_id] = i

        if not case.question.strip():
            problems.append(f"case '{case.case_id or i}': empty question")

        if case.answerable:
            if not case.relevant_doc_ids:
                problems.append(
                    f"case '{case.case_id or i}': answerable but has no "
                    f"relevant_doc_ids — cannot be scored for retrieval"
                )
            if not case.expected_answer_contains:
                problems.append(
                    f"case '{case.case_id or i}': answerable but has no "
                    f"expected_answer_contains — cannot be scored for the answer"
                )

    if cases:
        unanswerable_count = sum(1 for c in cases if not c.answerable)
        if unanswerable_count == 0:
            problems.append(
                "dataset has zero answerable=false cases — you cannot detect "
                "hallucination without some. Aim for roughly a quarter of the "
                "dataset."
            )

    return problems
