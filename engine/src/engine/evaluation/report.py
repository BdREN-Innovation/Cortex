"""Render a scorecard people will actually read.

TEAM C OWNS THIS FILE.

Your audience is Teams A and B, and your purpose is to make them change
something. A wall of numbers gets skimmed; a table of failing cases gets
fixed.

Decisions you own
-----------------
* What format? Markdown renders in a pull request and a terminal both,
  needs no extra tooling, and is easy to diff between two scorecards.
* How many failing cases to show? Enough to be actionable, not so many that
  the table itself gets skimmed. Cap it and say how many were omitted.
* Retrieval vs generation, always separated: high recall with a low answer
  score means the prompt is wrong; low recall means chunking or embeddings
  are wrong. Those are different files and different people.
"""

from __future__ import annotations

from engine.contracts.evaluation import EvalResult, RunReport

_MAX_FAILURES_SHOWN = 20


def render_report(report: RunReport) -> str:
    """Render a RunReport as a Markdown scorecard.

    Sections, in order: headline pass rate (split answerable/unanswerable),
    the retrieval-vs-generation breakdown, hallucination rate called out on
    its own, then a table of failing cases capped at _MAX_FAILURES_SHOWN.
    """
    agg = report.aggregate
    lines: list[str] = []

    lines.append(f"# Evaluation report — {report.dataset or report.run_id}")
    lines.append("")
    lines.append(f"- Run: `{report.run_id}`")
    lines.append(f"- Index: `{report.index_id}`")
    lines.append(f"- Cases: {report.case_count}")
    lines.append(f"- Started: {report.started_at}  Finished: {report.finished_at}")
    lines.append("")

    lines.append("## Headline")
    lines.append("")
    lines.append(
        f"**Pass rate: {_pct(agg.get('pass_rate', 0.0))}** "
        f"(answerable: {_pct(agg.get('pass_rate_answerable', 0.0))}, "
        f"unanswerable: {_pct(agg.get('pass_rate_unanswerable', 0.0))})"
    )
    lines.append("")
    lines.append(
        "A single blended number hides the split that matters: a system can "
        "score well overall by answering everything and refusing nothing, "
        "which is a system that cannot be trusted."
    )
    lines.append("")

    lines.append("## Hallucination rate")
    lines.append("")
    halluc = agg.get("hallucination_rate", 0.0)
    lines.append(f"**{_pct(halluc)}** of unanswerable questions were answered anyway.")
    lines.append(
        "This is the number that decides whether this system is trustworthy — "
        "everything else is a quality-of-service metric."
    )
    lines.append("")

    lines.append("## Retrieval vs generation")
    lines.append("")
    lines.append("| Metric | Value | Answers this |")
    lines.append("|---|---|---|")
    lines.append(
        f"| Mean recall@5 | {_num(agg.get('mean_recall_at_k', 0.0))} | "
        f"Were the right documents even retrieved? |"
    )
    lines.append(
        f"| Mean MRR | {_num(agg.get('mean_mrr', 0.0))} | "
        f"How far down the ranking was the first right document? |"
    )
    lines.append(
        f"| Mean nDCG@5 | {_num(agg.get('mean_ndcg_at_k', 0.0))} | "
        f"How good was the whole ranking, not just the first hit? |"
    )
    lines.append(
        f"| Mean answer score | {_num(agg.get('mean_answer_score', 0.0))} | "
        f"Given the right documents, was the answer right? |"
    )
    lines.append(
        f"| Mean citation precision | {_num(agg.get('mean_citation_precision', 0.0))} | "
        f"Did it cite what it actually used? |"
    )
    lines.append("")
    lines.append(
        "High recall with a low answer score points at the prompt or "
        "generation step. Low recall points at chunking or embeddings. "
        "Those are different fixes for different people."
    )
    lines.append("")

    failing = [r for r in report.results if not r.passed]
    lines.append(f"## Failing cases ({len(failing)} of {report.case_count})")
    lines.append("")
    if not failing:
        lines.append("None. Every case passed.")
    else:
        shown = failing[:_MAX_FAILURES_SHOWN]
        lines.append("| Case | Question | Expected | Got | Retrieved docs | Reason |")
        lines.append("|---|---|---|---|---|---|")
        for r in shown:
            lines.append(_failure_row(r))
        if len(failing) > _MAX_FAILURES_SHOWN:
            lines.append("")
            lines.append(
                f"...and {len(failing) - _MAX_FAILURES_SHOWN} more, omitted for length."
            )
    lines.append("")

    return "\n".join(lines)


def _failure_row(r: EvalResult) -> str:
    question = _cell(r.question)
    answer_snippet = _cell(r.answer_text[:80])
    retrieved = _cell(", ".join(r.retrieved_doc_ids[:3]))
    reason = _cell(r.failure_reason)
    expected = "(refuse)" if not r.answerable else "(see dataset)"
    return f"| `{r.case_id}` | {question} | {expected} | {answer_snippet} | {retrieved} | {reason} |"


def _cell(value: str) -> str:
    """Escape a value for a Markdown table cell: no pipes, no newlines."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _num(value: float) -> str:
    return f"{value:.3f}"
