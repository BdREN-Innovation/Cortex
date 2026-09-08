"""engine crawl | extract | index | ask | eval

Given to you, and deliberately thin: each command parses arguments, loads a
YAML config, and hands both to one team's package. No business logic lives
here, so the CLI never becomes a fourth thing to own.

It is also deliberately incurious about your design. Command-line overrides are
merged into the config dict and passed to your `from_dict`, rather than being
poked into named dataclass fields — so renaming a config key is a change in one
place, yours, not a change here as well. Nothing in this file constrains what
you call your providers, your backends or your metrics.

What it does still touch, and the only places a change of yours could reach it:

  * the frozen contracts — Answer, Citation, RunReport
  * each config class's `from_dict`
  * a handful of config KEY names, when a command-line flag overrides one:
    `site`, `max_pages`, `min_text_chars`, `embedding_provider`, and the
    nested `rag` block. Rename one of those in your YAML and you will want to
    rename it here too.

If you do need to change it: it is shared, so all three teams review it.
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


def _overrides(**kwargs) -> dict:
    """Only the flags the user actually passed, so an unset flag never
    overwrites a value from the config file with a default."""
    return {key: value for key, value in kwargs.items() if value is not None and value != ""}


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
    print(f"\npages    -> {out_dir / 'pages.jsonl'}")
    print(f"manifest -> {out_dir / 'manifest.json'}")
    print(f"\nnext: engine extract --run {out_dir}")
    return 0


# ── extract ────────────────────────────────────────────────────────────────
def cmd_extract(args: argparse.Namespace) -> int:
    from engine.knowledge.documents import ExtractConfig, extract_documents

    payload = _load_yaml(args.config) if args.config else {}
    if args.min_text_chars is not None:
        payload["min_text_chars"] = args.min_text_chars

    out_path = extract_documents(args.run, ExtractConfig.from_dict(payload), args.out)
    print(f"\ndocuments -> {out_path}")
    print(f"\nnext: engine index --documents {out_path}")
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

    payload = _load_yaml(args.config) if args.config else {}
    payload.update(_overrides(provider=args.provider, model=args.model, top_k=args.top_k))

    retriever = load_retriever(args.index)
    result = answer(args.question, retriever, RagConfig.from_dict(payload))

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
    from engine.knowledge.retriever import load_retriever

    payload = _load_yaml(args.config) if args.config else {}
    # Merged into the nested rag block rather than assigned to attributes, so
    # EvalConfig and RagConfig stay free to change shape.
    rag_overrides = _overrides(provider=args.provider, model=args.model)
    if rag_overrides:
        payload["rag"] = {**payload.get("rag", {}), **rag_overrides}

    config = EvalConfig.from_dict(payload)
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

    # Whatever aggregates the evaluation team decided to produce. This does not
    # know or care what the metrics are called.
    print()
    for key, value in report.aggregate.items():
        shown = f"{value:.3f}" if isinstance(value, float) else value
        print(f"  {key:<28} {shown}")
    print(f"\nreport -> {out_dir}")

    # Non-zero exit lets CI gate on a regression. Which metric gates the build
    # is named on the command line, so it is not fixed here either.
    if args.gate_metric and args.gate_min is not None:
        actual = report.aggregate.get(args.gate_metric)
        if actual is None:
            print(f"\nerror: no aggregate called {args.gate_metric!r}", file=sys.stderr)
            return 2
        if actual < args.gate_min:
            print(
                f"\nFAIL: {args.gate_metric} {actual} is below {args.gate_min}",
                file=sys.stderr,
            )
            return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine", description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--data-root", default=DEFAULT_DATA_ROOT, help="where artifacts are written"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="capture a site: raw bytes + pages.jsonl")
    crawl.add_argument("--config", required=True, help="configs/crawl.yaml")
    crawl.add_argument("--site", help="override the site name in the config")
    crawl.add_argument("--max-pages", type=int, help="override the page budget")
    crawl.set_defaults(func=cmd_crawl)

    extract = sub.add_parser(
        "extract", help="turn a crawl run's captured bytes into documents.jsonl"
    )
    extract.add_argument("--run", required=True, help="a data/sites/<site>/<run> directory")
    extract.add_argument("--config", help="configs/extract.<site>.yaml")
    extract.add_argument("--out", help="defaults to documents.jsonl inside the run directory")
    extract.add_argument("--min-text-chars", type=int, help="override the thin-page threshold")
    extract.set_defaults(func=cmd_extract)

    index = sub.add_parser("index", help="build a vector index from documents.jsonl")
    index.add_argument("--documents", required=True, help="path to documents.jsonl")
    index.add_argument("--config", help="configs/index.yaml")
    index.add_argument("--site")
    index.add_argument("--provider", help="embedding provider, overrides the config")
    index.set_defaults(func=cmd_index)

    ask = sub.add_parser("ask", help="ask the knowledge base a question")
    ask.add_argument("question")
    ask.add_argument("--index", required=True, help="path to an index directory")
    ask.add_argument("--config", help="configs/eval.<site>.yaml, for the rag settings")
    ask.add_argument("--provider", help="generation provider, overrides the config")
    ask.add_argument("--model", help="overrides the config")
    ask.add_argument("--top-k", type=int, help="overrides the config")
    ask.set_defaults(func=cmd_ask)

    evaluate = sub.add_parser("eval", help="score the system against a golden dataset")
    evaluate.add_argument("--dataset", required=True, help="datasets/<site>/golden.v1.yaml")
    evaluate.add_argument("--index", required=True)
    evaluate.add_argument("--config", help="configs/eval.yaml")
    evaluate.add_argument("--provider", help="generation provider, overrides the config")
    evaluate.add_argument("--model", help="overrides the config")
    evaluate.add_argument("--gate-metric", help="name of an aggregate to gate on, e.g. in CI")
    evaluate.add_argument("--gate-min", type=float, help="exit 1 when --gate-metric is below this")
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
