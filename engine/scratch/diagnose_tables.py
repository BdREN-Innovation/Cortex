"""Diagnostic: compare pdfplumber table-detection strategies and a
false-positive filter, on a single PDF, before touching pdf.py for real.

Usage:
    uv run python scratch/diagnose_tables.py corpus/cuet/_files/de1bedf5__69e479fa7ce5b.pdf
"""

from __future__ import annotations

import sys

import pdfplumber


def is_real_table(table: list[list]) -> tuple[bool, str]:
    """Heuristic filter for pdfplumber's extract_tables() output.
    Returns (keep, reason) so we can see why something was dropped."""
    if not table:
        return False, "empty"

    n_rows = len(table)
    n_cols = max(len(r) for r in table)

    if n_cols < 2:
        return False, f"single-column ({n_cols} col)"

    # The recurring false-positive signature seen in the MME syllabus:
    # a 2x2 "table" whose only content is the repeating section header.
    flat_cells = [str(c).strip() for row in table for c in row if c]
    flat_lower = {c.lower() for c in flat_cells}
    if n_rows == 2 and n_cols == 2 and "course content" in flat_lower:
        return False, "repeated section-header noise"

    total_cells = n_rows * n_cols
    non_empty = sum(1 for row in table for c in row if c and str(c).strip())
    fill_ratio = non_empty / total_cells if total_cells else 0
    if fill_ratio < 0.5:
        return False, f"sparse ({fill_ratio:.0%} filled)"

    return True, "kept"


def run_strategy(path: str, strategy: str) -> dict[int, list]:
    settings = {
        "vertical_strategy": strategy,
        "horizontal_strategy": strategy,
    }
    results: dict[int, list] = {}
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            tables = page.extract_tables(table_settings=settings)
            if tables:
                results[i] = tables
    return results


def summarize(label: str, results: dict[int, list]) -> None:
    total = sum(len(v) for v in results.values())
    print(f"\n=== {label}: {total} raw tables across {len(results)} pages ===")

    kept, dropped = [], []
    for page_num, tables in results.items():
        for t in tables:
            ok, reason = is_real_table(t)
            (kept if ok else dropped).append((page_num, t, reason))

    print(f"  kept:    {len(kept)}")
    print(f"  dropped: {len(dropped)}")

    print("\n  --- dropped (with reason) ---")
    for page_num, t, reason in dropped[:15]:
        rows, cols = len(t), (len(t[0]) if t else 0)
        print(f"  page {page_num}: {rows}x{cols} | {reason}")
    if len(dropped) > 15:
        print(f"  ... and {len(dropped) - 15} more")

    print("\n  --- kept (sample) ---")
    for page_num, t, _ in kept[:8]:
        rows, cols = len(t), (len(t[0]) if t else 0)
        print(f"  page {page_num}: {rows}x{cols} | first row: {t[0]}")
    if len(kept) > 8:
        print(f"  ... and {len(kept) - 8} more")


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: diagnose_tables.py <path-to-pdf>")
        sys.exit(1)

    path = sys.argv[1]

    lines_results = run_strategy(path, "lines")
    summarize("STRATEGY: lines (default)", lines_results)

    text_results = run_strategy(path, "text")
    summarize("STRATEGY: text (alignment-based)", text_results)


if __name__ == "__main__":
    main()