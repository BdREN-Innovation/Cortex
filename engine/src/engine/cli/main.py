"""engine crawl | index | ask | eval

Thin wrappers only: every command parses arguments, loads a YAML config and
calls into one team's package. No business logic lives here, so the CLI never
becomes a fourth thing to own.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

DEFAULT_DATA_ROOT = "data"


def _load_yaml(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
    )


# ── crawl ──────────────────────────────────────────────────────────────────
def cmd_crawl(args: argparse.Namespace) -> int:
    from engine.crawler.pipeline import CrawlConfig, crawl

    payload = _load_yaml(args.config)
    if args.site:
        payload["site"] = args.site
    if args.max_pages:
        payload["max_pages"] = args.max_pages

    config = CrawlConfig.from_dict(payload)
    out_dir = crawl(config, out_root=args.data_root)
    print(f"\ndocuments -> {out_dir / 'documents.jsonl'}")
    print(f"manifest  -> {out_dir / 'manifest.json'}")
    return 0


# ── index ──────────────────────────────────────────────────────────────────
def cmd_index(args: argparse.Namespace) -> int:
    from engine.knowledge.indexer import IndexConfig, build_index

    payload = _load_yaml(args.config) if args.config else {}
    if args.site:
        payload["site"] = args.site
    if args.provider:
        payload["embedding_provider"] = args.provider

    config = IndexConfig.from_dict(payload)
    index_dir = build_index(args.documents, out_root=args.data_root, config=config)
    print(f"\nindex -> {index_dir}")
    return 0


# ── ask ────────────────────────────────────────────────────────────────────
def cmd_ask(args: argparse.Namespace) -> int:
    from engine.knowledge.rag import RagConfig, answer
    from engine.knowledge.retriever import load_retriever

    retriever = load_retriever(args.index)
    config = RagConfig(provider=args.provider, model=args.model, top_k=args.top_k)
    result = answer(args.question, retriever, config)

    print(f"\n{result.text}\n")
    if result.citations:
        print("Sources:")
        for position, citation in enumerate(result.citations, start=1):
            where = " > ".join(citation.section_path) if citation.section_path else citation.title
            print(f"  [{position}] {where or citation.canonical_url}")
            print(f"      {citation.canonical_url}")
    print(f"\n({result.latency_ms} ms, {len(result.retrieved_chunk_ids)} chunks retrieved)")
    return 0


# ── eval ───────────────────────────────────────────────────────────────────
def cmd_eval(args: argparse.Namespace) -> int:
    from engine.evaluation.dataset import load_dataset
    from engine.evaluation.report import write_report
    from engine.evaluation.runner import EvalConfig, run_evaluation
    from engine.knowledge.rag import RagConfig
    from engine.knowledge.retriever import load_retriever

    payload = _load_yaml(args.config) if args.config else {}
    config = EvalConfig.from_dict(payload)
    if args.provider:
        config.rag = config.rag or RagConfig()
        config.rag.provider = args.provider
        config.rag.model = args.model or config.rag.model

    cases = load_dataset(args.dataset)
    retriever = load_retriever(args.index)

    report = run_evaluation(
        cases,
        retriever,
        config,
        dataset_name=str(args.dataset),
        index_id=getattr(retriever, "index_id", ""),
    )
    out_dir = Path(args.data_root) / "runs" / report.run_id
    write_report(report, out_dir)

    agg = report.aggregate
    print(f"\npass rate        {agg.get('pass_rate', 0):.1%}")
    print(f"  answerable     {agg.get('pass_rate_answerable', 0):.1%}")
    print(f"  unanswerable   {agg.get('pass_rate_unanswerable', 0):.1%}")
    print(f"hallucination    {agg.get('hallucination_rate', 0):.1%}")
    print(f"\nreport -> {out_dir / 'report.md'}")

    # Non-zero exit lets CI gate on a regression.
    if args.min_pass_rate and agg.get("pass_rate", 0) < args.min_pass_rate:
        print(f"\nFAIL: pass rate below threshold {args.min_pass_rate:.1%}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine", description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT, help="where artifacts are written")
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="fetch a site and write documents.jsonl")
    crawl.add_argument("--config", required=True, help="configs/crawl.yaml")
    crawl.add_argument("--site", help="override the site name in the config")
    crawl.add_argument("--max-pages", type=int, help="override the page budget")
    crawl.set_defaults(func=cmd_crawl)

    index = sub.add_parser("index", help="build a vector index from documents.jsonl")
    index.add_argument("--documents", required=True, help="path to documents.jsonl")
    index.add_argument("--config", help="configs/index.yaml")
    index.add_argument("--site")
    index.add_argument("--provider", choices=["hash", "openai"], help="embedding provider")
    index.set_defaults(func=cmd_index)

    ask = sub.add_parser("ask", help="ask the knowledge base a question")
    ask.add_argument("question")
    ask.add_argument("--index", required=True, help="path to an index directory")
    ask.add_argument("--provider", default="extractive", choices=["extractive", "openai", "anthropic"])
    ask.add_argument("--model", default="")
    ask.add_argument("--top-k", type=int, default=5)
    ask.set_defaults(func=cmd_ask)

    evaluate = sub.add_parser("eval", help="score the system against a golden dataset")
    evaluate.add_argument("--dataset", required=True, help="datasets/<site>/golden.v1.yaml")
    evaluate.add_argument("--index", required=True)
    evaluate.add_argument("--config", help="configs/eval.yaml")
    evaluate.add_argument("--provider", choices=["extractive", "openai", "anthropic"])
    evaluate.add_argument("--model", default="")
    evaluate.add_argument("--min-pass-rate", type=float, default=0.0, help="exit 1 below this")
    evaluate.set_defaults(func=cmd_eval)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
