"""List every document from a crawl run that has no golden-dataset question yet.

Usage:
    uv run python scripts/check_unused.py \
        data/sites/bdren/bdren-20260913T073128Z/documents.jsonl \
        datasets/bdren/golden.v1.yaml
"""
import json
import sys

import yaml


def main() -> None:
    documents_path, golden_path = sys.argv[1], sys.argv[2]

    with open(documents_path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]

    with open(golden_path, encoding="utf-8") as f:
        golden = yaml.safe_load(f)

    used_ids = {c.get("doc_id") for c in golden.get("cases", []) if c.get("doc_id")}
    unused = [r for r in rows if r["doc_id"] not in used_ids]

    print(f"{len(unused)} unused documents\n")
    for r in unused:
        text = (r.get("text") or "").strip().replace("\n", " ")
        url = r.get("url") or r.get("canonical_url") or ""
        print(f"{r['doc_id']}  {url}")
        print(f"   {text[:140]}")
        print()


if __name__ == "__main__":
    main()