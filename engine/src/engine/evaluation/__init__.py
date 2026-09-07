"""Team 3: a golden dataset and the harness that scores the system against it."""

from engine.evaluation.dataset import load_dataset, validate_dataset
from engine.evaluation.runner import EvalConfig, run_evaluation

__all__ = ["load_dataset", "validate_dataset", "EvalConfig", "run_evaluation"]
