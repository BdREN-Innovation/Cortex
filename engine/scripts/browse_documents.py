#!/usr/bin/env python3
"""Read a documents.jsonl so you can write questions against it.

Team C's authoring tool. Writing 60 good cases by hand is only practical if
reading the corpus is easy and the doc_id is right there next to the text.

    # list what is in the corpus
    uv run python scripts/browse_documents.py datasets/acme/documents.sample.jsonl

    # read one document in full, with a ready-to-paste YAML skeleton
    uv run python scripts/browse_documents.py <path> --show 7c9449099579549c

    # find the document containing a fact you want to ask about
    uv run python scripts/browse_documents.py <path> --grep "business days"

    # coverage: which documents does your dataset already ask about?
    uv run python scripts/browse_documents.py <path> --coverage datasets/acme/golden.v1.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(
            f"error: {path} not found.\n"
            "Team A and B have not produced a corpus yet — start from "
            "datasets/acme/documents.sample.jsonl, which ships with the repo."
        )
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def cmd_list(docs: list[dict]) -> None:
    print(f"\n{len(docs)} documents\n")
    print(f"  {'doc_id':18} {'type':5} {'chars':>6}  title")
    print(f"  {'-' * 18} {'-' * 5} {'-' * 6}  {'-' * 40}")
    for doc in docs:
        print(
            f"  {doc['doc_id']:18} {doc.get('doc_type', 'page'):5} "
            f"{len(doc['text']):6}  {doc['title'][:60]}"
        )
    pdfs = sum(1 for d in docs if d.get("doc_type") == "pdf")
    print(f"\n  {len(docs) - pdfs} pages, {pdfs} PDFs")
    tables = sum(1 for d in docs if "| --- |" in d["text"])
    print(f"  {tables} documents contain a table — ask at least one question about each\n")


def cmd_show(docs: list[dict], doc_id: str) -> None:
    matches = [d for d in docs if d["doc_id"].startswith(doc_id)]
    if not matches:
        sys.exit(f"error: no document whose id starts with {doc_id!r}")
    for doc in matches:
        print()
        print("=" * 78)
        print(f"  {doc['title']}")
        print(f"  {doc['canonical_url']}")
        print(
            f"  doc_id {doc['doc_id']}   type {doc.get('doc_type', 'page')}   "
            f"breadcrumb {' > '.join(doc.get('section_path') or []) or '(none)'}"
        )
        print("=" * 78)
        print()
        print(doc["text"])
        print()
        print("-" * 78)
        print("  Skeleton — copy into your golden.v1.yaml and fill in:")
        print(f"""
  - case_id: {re.sub(r'[^a-z0-9]+', '-', doc['title'].lower()).strip('-')[:28]}-CHANGEME
    question: ""
    relevant_doc_ids: ["{doc['doc_id']}"]
    expected_answer_contains: [""]     # short, factual, hard to paraphrase
    tags: []
""")


def cmd_grep(docs: list[dict], pattern: str) -> None:
    rx = re.compile(pattern, re.I)
    hits = 0
    for doc in docs:
        for line in doc["text"].splitlines():
            if rx.search(line):
                hits += 1
                print(f"\n  {doc['doc_id']}  {doc['title']}")
                print(f"    {line.strip()[:100]}")
    if not hits:
        print(f"\n  no match for {pattern!r} — the corpus may genuinely not cover it.")
        print("  That makes it a good candidate for an `answerable: false` case.\n")
    else:
        print(f"\n  {hits} matching lines\n")


def cmd_coverage(docs: list[dict], dataset_path: Path) -> None:
    try:
        import yaml
    except ImportError:
        sys.exit("error: PyYAML is not installed. Run: uv sync --extra dev")

    payload = yaml.safe_load(dataset_path.read_text(encoding="utf-8")) or {}
    cases = payload.get("cases", payload if isinstance(payload, list) else [])

    asked: dict[str, int] = {}
    answerable = unanswerable = 0
    for case in cases:
        if case.get("answerable", True):
            answerable += 1
            for doc_id in case.get("relevant_doc_ids", []):
                asked[doc_id] = asked.get(doc_id, 0) + 1
        else:
            unanswerable += 1

    print(f"\n  {len(cases)} cases: {answerable} answerable, {unanswerable} unanswerable")
    share = unanswerable / len(cases) if cases else 0
    verdict = "good" if 0.15 <= share <= 0.35 else "TOO FEW — aim for ~25%"
    print(f"  unanswerable share: {share:.0%}  ({verdict})\n")

    print(f"  {'doc_id':18} {'cases':>5}  title")
    print(f"  {'-' * 18} {'-' * 5}  {'-' * 40}")
    uncovered = 0
    for doc in docs:
        count = asked.get(doc["doc_id"], 0)
        if not count:
            uncovered += 1
        flag = "  <-- no questions" if not count else ""
        print(f"  {doc['doc_id']:18} {count:5}  {doc['title'][:44]}{flag}")

    unknown = set(asked) - {d["doc_id"] for d in docs}
    if unknown:
        print(f"\n  WARNING: {len(unknown)} relevant_doc_ids are not in this corpus:")
        for doc_id in sorted(unknown):
            print(f"    {doc_id}")
        print("  Either the dataset is stale or you are pointing at the wrong corpus.")
    if uncovered:
        print(f"\n  {uncovered} documents have no questions. A document nobody asks about")
        print("  is a document you are not testing.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("documents", type=Path, help="path to a documents.jsonl")
    parser.add_argument("--show", metavar="DOC_ID", help="print one document in full")
    parser.add_argument("--grep", metavar="PATTERN", help="find which document states a fact")
    parser.add_argument(
        "--coverage",
        type=Path,
        metavar="DATASET",
        help="which documents your dataset already covers",
    )
    args = parser.parse_args()

    docs = load(args.documents)
    if args.show:
        cmd_show(docs, args.show)
    elif args.grep:
        cmd_grep(docs, args.grep)
    elif args.coverage:
        cmd_coverage(docs, args.coverage)
    else:
        cmd_list(docs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
