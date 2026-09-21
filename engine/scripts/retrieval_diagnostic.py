import argparse
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from engine.contracts.evaluation import EvalCase
from engine.knowledge.retriever import load_retriever


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    raw = yaml.safe_load(Path(args.dataset).read_text(encoding="utf-8"))
    cases = [EvalCase.from_dict(c) for c in raw["cases"]]
    retriever = load_retriever(args.index)

    rows = []
    for case in cases:
        chunks = retriever.retrieve(case.question, top_k=args.top_k)
        docs = list(dict.fromkeys(c.doc_id for c in chunks))
        rel = set(case.relevant_doc_ids)
        rank = next((i + 1 for i, d in enumerate(docs) if d in rel), None)
        rows.append({
            "id": case.case_id,
            "answerable": case.answerable,
            "top1": float(chunks[0].score) if chunks else 0.0,
            "rank": rank,
            "recall": len(set(docs) & rel) / len(rel) if rel else 0.0,
            "top_doc": docs[0] if docs else "",
        })

    ans = [r for r in rows if r["answerable"]]
    una = [r for r in rows if not r["answerable"]]
    k = args.top_k
    print(f"answerable={len(ans)} unanswerable={len(una)}")
    print(f"hit@1      {mean(r['rank'] == 1 for r in ans):.3f}")
    print(f"recall@{k}   {mean(r['recall'] for r in ans):.3f}")
    print(f"MRR        {mean(1 / r['rank'] if r['rank'] else 0 for r in ans):.3f}")

    print("\nunanswerable, highest top-1 score first:")
    for r in sorted(una, key=lambda r: -r["top1"]):
        print(f"  {r['id']}  {r['top1']:.3f}  {r['top_doc']}")

    print("\nanswerable with no relevant doc in top-k:")
    print("  " + ", ".join(r["id"] for r in ans if not r["rank"]))

    lo = min(r["top1"] for r in rows)
    hi = max(r["top1"] for r in rows)
    print("\nmin_score  unans_refused  ans_wrongly_refused")
    for i in range(21):
        t = lo + (hi - lo) * i / 20
        refused = mean(r["top1"] < t for r in una)
        wrong = mean(r["top1"] < t for r in ans if r["rank"])
        print(f"{t:9.3f}  {refused:13.2f}  {wrong:19.2f}")


if __name__ == "__main__":
    main()