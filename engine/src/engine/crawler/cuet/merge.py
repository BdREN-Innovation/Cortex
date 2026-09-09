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

from urllib.parse import urlsplit

from . import config, handover
from .paths import canonical
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



def write_known_gaps(out: Path, planned: dict[str, str],
                     captured: set[str]) -> Path:
    """State, in the corpus, what is missing and why.

    A corpus that is silently short of two pages looks the same as one that is
    complete. Anyone reading it later - Team B, or whoever picks this up next
    term - has no way to tell an unreachable host from an oversight unless the
    corpus says so itself.

    So the gap is written down next to the data rather than left in a commit
    message or a person's memory. Each entry names the URL, the reason, and
    whether anything can be done about it.
    """
    entries = []
    for url, why in sorted(planned.items()):
        if url in captured:
            continue
        host = urlsplit(url).netloc
        reason = config.UNRESOLVABLE_HOSTS.get(host)
        entries.append({
            "url": url,
            "planned_because": why,
            "state": "unreachable" if reason else "not captured",
            "reason": reason or "planned but not captured; see _meta/errors.json",
            "actionable": not reason,
        })

    payload = {
        "note": ("Planned URLs that are not in the corpus, with the reason for "
                 "each. An entry with actionable=false cannot be fixed by "
                 "re-running: the host does not resolve."),
        "generated_by": "--stage merge",
        "count": len(entries),
        "gaps": entries,
    }
    path = out / "_meta" / "known_gaps.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    if entries:
        log.info("known gaps: %d planned URL(s) not captured, reasons in %s",
                 len(entries), path.name)
    return path


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

    # Written before the README so the README can quote a settled number.
    planned: dict[str, str] = {}
    plan_path = out / "_meta" / "urls.txt"
    if plan_path.exists():
        for line in plan_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            url, _, why = line.partition("\t")
            planned[canonical(url.strip())] = why.lstrip("# ").strip()
    write_known_gaps(out, planned,
                     {canonical(d["canonical_url"]) for d in ordered_docs})

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
