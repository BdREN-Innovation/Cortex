#!/usr/bin/env python3
"""Per-team progress: how much of the scaffold has been filled in.

    uv run python scripts/progress.py            # summary
    uv run python scripts/progress.py --detail   # every function, file by file

Every function in src/engine/ starts as a stub that raises NotImplementedError.
This walks the source with Python's own parser and counts how many still do.

It measures *coverage of the scaffold*, not correctness — a function that
returns the wrong answer counts as done here. Correctness is judged by running
the pipeline and reading the output, which is what the definition-of-done
checklist in each team's README is for.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
SRC = ENGINE / "src" / "engine"

TEAMS = [
    ("Team A", "crawler — capture a site", "crawler"),
    ("Team B", "knowledge — clean, embed, answer", "knowledge"),
    ("Team C", "evaluation — dataset and scoring", "evaluation"),
]


def _significant(node) -> list:
    """Body statements, ignoring the docstring."""
    return [
        n
        for n in node.body
        if not (
            isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )
    ]


def is_declaration(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A Protocol method: body is just `...`. A type declaration, never
    something anyone implements, so it is not counted as work."""
    body = _significant(node)
    return (
        len(body) == 1
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and body[0].value.value is Ellipsis
    )


def is_stub(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A stub is a docstring plus `raise NotImplementedError` and nothing else."""
    body = _significant(node)
    return (
        len(body) == 1
        and isinstance(body[0], ast.Raise)
        and "NotImplementedError" in ast.dump(body[0])
    )


def scan(package: str) -> dict[str, tuple[int, int]]:
    """{filename: (done, total)} for one team package."""
    out: dict[str, tuple[int, int]] = {}
    for path in sorted((SRC / package).rglob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fns = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not is_declaration(n)
        ]
        if not fns:
            continue
        done = sum(1 for f in fns if not is_stub(f))
        out[str(path.relative_to(SRC))] = (done, len(fns))
    return out


def bar(done: int, total: int, width: int = 24) -> str:
    if not total:
        return " " * width
    filled = round(width * done / total)
    return "█" * filled + "·" * (width - filled)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--detail", action="store_true", help="list every file and unfinished function"
    )
    args = parser.parse_args()

    print()
    overall_done = overall_total = 0

    for name, description, package in TEAMS:
        files = scan(package)
        done = sum(d for d, _ in files.values())
        total = sum(t for _, t in files.values())
        overall_done += done
        overall_total += total
        pct = (done / total * 100) if total else 0
        print(f"  {name:7} {description:36} {bar(done, total)}  {done:2}/{total:<3} {pct:4.0f}%")

        if args.detail:
            for filename, (fdone, ftotal) in files.items():
                mark = "✓" if fdone == ftotal else " "
                print(f"          {mark} {filename:34} {fdone:2}/{ftotal:<3}")
            print()

    print()
    pct = (overall_done / overall_total * 100) if overall_total else 0
    print(
        f"  {'TOTAL':7} {'functions implemented':36} "
        f"{bar(overall_done, overall_total)}  {overall_done:2}/{overall_total:<3} {pct:4.0f}%"
    )
    print()
    print("  Scaffold coverage only — it does not check that the code is correct.")
    print("  Run the pipeline and read the output for that; see each team's README.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
