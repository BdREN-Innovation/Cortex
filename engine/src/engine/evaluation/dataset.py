"""The golden dataset: questions with known-correct answers.

This file loads and validates it. Writing the dataset itself is the harder and
more valuable half of Team C's job — see datasets/ and the team README.

TEAM C OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

PyYAML   yaml.safe_load. Always safe_load, never load.

"""

from __future__ import annotations

from pathlib import Path

from engine.contracts.evaluation import EvalCase


def load_dataset(path: str | Path) -> list[EvalCase]:
    """Read `datasets/<site>/golden.v1.yaml` into EvalCases.

    Validate on load and raise with ALL the problems listed, not just the
    first. Someone fixing a 60-case dataset should get one report, not sixty
    round trips.
    """
    raise NotImplementedError


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
    raise NotImplementedError
