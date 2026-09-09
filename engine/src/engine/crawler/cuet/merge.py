"""Assemble the shards into one corpus. Spec §12.1.

Every corpus-wide file is built here and nowhere else:

    documents.jsonl   CleanDocument rows, the thing Team B embeds
    pages.jsonl       CrawledPage rows, the `engine extract --run` interface
    manifest.json     counts, errors, config
    _meta/found_*     the union of every portion's link discovery
    README.md         written by handover.py

All five are **generated files**. They are gitignored on purpose: a file that
four people each regenerate is a file four people conflict on, every time. The
shards under `_shards/` are the committed source of truth, one per portion, one
owner each.

    python -m engine.crawler.cuet --stage merge

runs in about a second, needs no network, and is what you do after `git pull`.

Ordering is deterministic — documents sort by `doc_id`, files and pages sort by
URL — so two people who merge the same shards get byte-identical output. That is
what makes "just regenerate it" a real answer rather than a hopeful one.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import config, handover
from .content import SHARDS

log = logging.getLogger(__name__)


class NoShardsError(SystemExit):
    """Raised with an actionable message rather than an empty corpus."""


def load_shards(out: Path) -> list[dict]:
    shard_dir = out / SHARDS
    if not shard_dir.is_dir():
        raise NoShardsError(
            f"{shard_dir} does not exist. Nothing has been built yet. Run\n"
            f"    python -m engine.crawler.cuet --stage content --out {out}\n"
            f"or pull the committed shards."
        )
    paths = sorted(shard_dir.glob("*.json"))
    if not paths:
        raise NoShardsError(f"{shard_dir} holds no shards. See --stage content.")

    shards = []
    for path in paths:
        try:
            shards.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            # One corrupt shard must not silently shrink the corpus: a merge
            # that quietly drops a portion looks exactly like a portion nobody
            # has built yet.
            raise NoShardsError(f"{path} is not valid JSON: {exc}") from exc
        log.info("shard %-24s %5d documents", path.name,
                 len(shards[-1].get("documents", [])))
    return shards


def run(out: Path | None = None) -> dict:
    """Merge every shard into the corpus files. Returns the counts."""
    out = out or config.OUT
    shards = load_shards(out)

    documents: dict[str, dict] = {}
    pages: dict[str, dict] = {}
    found_files: dict[str, dict] = {}
    found_pages: set[str] = set()
    warnings: list[str] = []
    portions: list[str] = []
    collisions: list[str] = []

    for shard in shards:
        portions.extend(shard.get("portions", []))
        warnings.extend(shard.get("warnings", []))

        for doc in shard.get("documents", []):
            doc_id = doc["doc_id"]
            # Two portions claiming one document is a real defect — someone's
            # builder has wandered into someone else's slice. Report it rather
            # than letting last-shard-wins decide.
            if doc_id in documents and documents[doc_id] != doc:
                collisions.append(f"document:{doc_id}")
            documents[doc_id] = doc

        for page in shard.get("pages", []):
            pages[page["page_id"]] = page

        for record in shard.get("found_files", []):
            url = record["url"]
            existing = found_files.get(url)
            if existing is None:
                found_files[url] = dict(record)
                continue
            # The same PDF is linked from several portions. Union the sources
            # rather than letting the last shard read decide who linked it.
            merged = set(existing.get("linked_from", [])) | set(
                record.get("linked_from", []))
            existing.update({k: v for k, v in record.items()
                             if k != "linked_from" and v})
            existing["linked_from"] = sorted(merged)
            existing["download"] = existing.get("download") or record.get("download")

        found_pages.update(shard.get("found_pages", []))

    if collisions:
        log.warning("%d document id(s) claimed by more than one portion: %s",
                    len(collisions), ", ".join(collisions[:5]))
        warnings.extend(collisions)

    ordered_docs = [documents[k] for k in sorted(documents)]
    ordered_pages = [pages[k] for k in sorted(pages)]

    _write_jsonl(out / "documents.jsonl", ordered_docs)
    written = handover.write_pages_jsonl(ordered_pages, out)

    meta_dir = out / "_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "found_files.txt").write_text(
        "\n".join(sorted(found_files)) + "\n", encoding="utf-8")
    (meta_dir / "found_files.json").write_text(
        json.dumps([found_files[k] for k in sorted(found_files)],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (meta_dir / "found_pages.txt").write_text(
        "\n".join(sorted(found_pages)) + "\n", encoding="utf-8")

    handover.write_readme(out)
    handover.write_manifest(
        out,
        run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        started=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        finished=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        documents=len(ordered_docs), pages=written,
        files={"downloaded": sum(1 for f in found_files.values()
                                 if f.get("download"))},
        errors=warnings,
        portions=sorted(set(portions)),
    )

    log.info("merge: %d documents, %d pages, %d files, %d warnings from %d shard(s)",
             len(ordered_docs), written, len(found_files), len(warnings), len(shards))
    return {"documents": len(ordered_docs), "pages": written,
            "files": len(found_files), "warnings": len(warnings),
            "shards": len(shards), "portions": sorted(set(portions))}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
