"""Turn a RunReport into something a human will actually read.

The audience is Teams A and B, and the purpose is to make them change
something. A wall of numbers gets skimmed; five failing questions with their
retrieved documents next to them get fixed.

TEAM C OWNS THIS FILE.

"""

from __future__ import annotations

from pathlib import Path

from engine.contracts.evaluation import RunReport


def to_markdown(report: RunReport) -> str:
    """Render a scorecard.

    Lead with the headline numbers, then — the part that earns its keep — a
    table of the FAILING cases showing the question, what was expected, what
    came back, and which documents were retrieved. That table is what Team B
    works from.

    Include the index id and dataset name so a report is reproducible.
    """
    raise NotImplementedError


def write_report(report: RunReport, out_dir: str | Path) -> Path:
    """Write report.json and report.md into out_dir; return the directory.

    Both formats on purpose: the markdown is for people, the JSON is so you can
    compare runs later and plot whether the numbers are going up.
    """
    raise NotImplementedError
