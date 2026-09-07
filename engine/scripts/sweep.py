#!/usr/bin/env python
"""Sweep one knob across the golden dataset and print a comparison table.

This is the harness earning its keep: never tune chunk size, top_k or the
refusal threshold by eyeballing a few answers — change one thing, re-score, and
read the table.

    uv run python scripts/sweep.py --index data/index/acme/<id> \
        --dataset datasets/acme/golden.v1.yaml --knob min_score --values 0.05,0.1,0.2
"""

from __future__ import annotations

import argparse
import logging

from engine.evaluation.dataset import load_dataset
from engine.evaluation.runner import EvalConfig, run_evaluation
from engine.knowledge.rag import RagConfig
from engine.knowledge.retriever import load_retriever


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--knob", default="min_score", choices=["min_score", "top_k"])
    parser.add_argument("--values", default="0.05,0.10,0.15,0.20,0.25,0.30")
    parser.add_argument("--provider", default="extractive")
    args = parser.parse_args()

    logging.getLogger("engine").setLevel(logging.WARNING)

    cases = load_dataset(args.dataset)
    retriever = load_retriever(args.index)
    cast = int if args.knob == "top_k" else float
    values = [cast(v) for v in args.values.split(",")]

    header = f"{args.knob:>10} | {'pass':>6} | {'answerable':>10} | {'unanswerable':>12} | {'halluc':>7}"
    print(header)
    print("-" * len(header))

    for value in values:
        rag = RagConfig(provider=args.provider, **{args.knob: value})
        config = EvalConfig(rag=rag, top_k=rag.top_k)
        agg = run_evaluation(cases, retriever, config).aggregate
        print(
            f"{value:>10} | {agg['pass_rate']:>5.1%} | {agg['pass_rate_answerable']:>9.1%} | "
            f"{agg['pass_rate_unanswerable']:>11.1%} | {agg['hallucination_rate']:>6.1%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
