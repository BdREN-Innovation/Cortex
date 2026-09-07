"""Render a RunReport as JSON plus a human-readable scorecard."""

from __future__ import annotations

from pathlib import Path

from engine.contracts.evaluation import RunReport
from engine.contracts.jsonio import write_json


def to_markdown(report: RunReport) -> str:
    agg = report.aggregate
    lines = [
        f"# Evaluation run {report.run_id}",
        "",
        f"- dataset: `{report.dataset}`",
        f"- index: `{report.index_id}`",
        f"- provider: `{report.config.get('rag_provider')}` "
        f"`{report.config.get('rag_model') or '-'}`",
        f"- finished: {report.finished_at}",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Pass rate (all) | **{agg.get('pass_rate', 0):.1%}** |",
        f"| Pass rate (answerable) | {agg.get('pass_rate_answerable', 0):.1%} |",
        f"| Pass rate (unanswerable) | {agg.get('pass_rate_unanswerable', 0):.1%} |",
        f"| Hallucination rate | {agg.get('hallucination_rate', 0):.1%} |",
        f"| Latency p50 | {agg.get('latency_ms_p50', 0):.0f} ms |",
        "",
        "## Retrieval (answerable cases)",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for key in sorted(k for k in agg if k.startswith(("recall", "ndcg", "mrr"))):
        lines.append(f"| {key} | {agg[key]:.3f} |")

    lines += [
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| answer_match | {agg.get('answer_match', 0):.3f} |",
        f"| citation_precision | {agg.get('citation_precision', 0):.3f} |",
        f"| refusal_correct | {agg.get('refusal_correct', 0):.3f} |",
        "",
        "## Failures",
        "",
    ]

    failures = [r for r in report.results if not r.passed]
    if not failures:
        lines.append("None — every case passed.")
    else:
        lines += ["| Case | Question | Why |", "|---|---|---|"]
        for result in failures:
            question = result.question.replace("|", "\\|")[:70]
            lines.append(f"| `{result.case_id}` | {question} | {result.failure_reason} |")

    lines += ["", f"_{len(failures)} of {report.case_count} cases failed._", ""]
    return "\n".join(lines)


def write_report(report: RunReport, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "report.json", report)
    (out_dir / "report.md").write_text(to_markdown(report), encoding="utf-8")
    return out_dir
