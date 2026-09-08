"""CLI: stage dispatch and run bookkeeping. Spec §5, §7.5, §7.6."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import audit, config, content, discover, files
from .api import Client

log = logging.getLogger("cuet_scraper")

STAGES = ("discover", "content", "plan", "capture", "files", "audit", "all")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
        stream=sys.stdout,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m cuet_scraper",
        description="Capture the CUET public website. API-first; the browser "
                    "is used only where the API does not reach.",
    )
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--out", type=Path, default=config.OUT)
    parser.add_argument("--limit", type=int, default=None,
                        help="take the first N items after all other filters, "
                             "so a first run of a new configuration is cheap")
    parser.add_argument("--section", action="append", default=None,
                        help="restrict to one section key; repeatable")
    parser.add_argument("--force", action="store_true",
                        help="ignore resume state and re-fetch")
    parser.add_argument("--verbose", action="store_true", help="DEBUG logging")
    args = parser.parse_args(argv)

    # An unknown section name is a fatal error listing the valid names, never a
    # silent empty run. Spec §5.
    if args.section:
        unknown = [s for s in args.section if s not in config.SECTIONS]
        if unknown:
            parser.error(
                f"unknown section(s): {', '.join(unknown)}. "
                f"Valid names: {', '.join(config.SECTIONS)}"
            )
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    if config.CONTACT.startswith("REPLACE_ME"):
        # A warning, not a refusal: blocking a smoke test over this would be
        # obstructive. But it is the first thing CUET sees, so it is loud.
        log.warning("USER_AGENT still contains the placeholder contact address. "
                    "Set config.CONTACT before any full run - spec §7.4.")

    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "_meta").mkdir(parents=True, exist_ok=True)

    client = Client()
    summary = {
        "run_id": run_id,
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "stage": args.stage,
        "urls_planned": 0, "pages_captured": 0, "cms_documents": 0,
        "failed_renders": 0, "not_found": 0, "errors": 0,
        "files_downloaded": 0, "files_bytes": 0, "images_skipped": 0,
        "config": {"delay": config.DELAY, "max_concurrent": config.MAX_CONCURRENT,
                   "user_agent": config.USER_AGENT, "obey_robots": config.OBEY_ROBOTS},
    }
    errors: list[dict] = []
    stages = ("discover", "content", "files", "audit") if args.stage == "all" \
        else (args.stage,)

    try:
        dump = None
        for stage in stages:
            if stage in ("discover", "plan"):
                result = discover.run(client, out)
                dump = result["dump"]
                summary["urls_planned"] = len(result["urls"])
                errors.extend({"stage": "discover", **f} for f in result["failures"])

            elif stage == "content":
                dump = dump or _load_dump(out)
                result = content.run(dump, out)
                summary["cms_documents"] = len(result.documents)
                summary["pages_captured"] = len(result.documents)
                for warning in result.warnings:
                    errors.append({"stage": "content", "error": warning})

            elif stage == "files":
                result = files.run(client, out, force=args.force, limit=args.limit)
                summary["files_downloaded"] = result["downloaded"]
                summary["files_bytes"] = result.get("bytes", 0)
                summary["images_skipped"] = result.get("images_skipped", 0)
                errors.extend(result["errors"])

            elif stage == "audit":
                report = audit.run(client, out)
                summary["undocumented_endpoints"] = report["undocumented"]

            elif stage == "capture":
                from . import capture               # imported late: needs crawl4ai
                result = capture.run(client, out, limit=args.limit,
                                     sections=args.section, force=args.force)
                summary["pages_captured"] += result["captured"]
                summary["failed_renders"] = result["failed_renders"]
                summary["not_found"] = result["not_found"]
                errors.extend(result["errors"])
    finally:
        client.close()
        finished = datetime.now(timezone.utc)
        summary["finished_at"] = finished.isoformat().replace("+00:00", "Z")
        summary["errors"] = len(errors)
        summary["requests_made"] = client.request_count

        # Written even on a fully successful run, so an empty array is an
        # explicit statement rather than a missing file. Spec §7.5.
        (out / "_meta" / "errors.json").write_text(
            json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "_meta" / "run.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        log.info("run %s finished in %.1fs, %d requests, %d errors",
                 run_id, (finished - started).total_seconds(),
                 client.request_count, len(errors))

    return 0


def _load_dump(out: Path) -> dict:
    path = out / "_meta" / "api_dump.json"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run --stage discover first.")
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
