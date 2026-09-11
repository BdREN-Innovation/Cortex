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



def write_provenance(out: Path, documents: list[dict], found_files: dict) -> Path:
    """Where every document and every PDF came from, as one machine-readable file.

    Team B receives text and PDFs with no way to answer "where did this come
    from?" unless the corpus says so. `source` already records api or browser,
    but that is a category, not an origin: it does not say WHICH endpoint built
    a document, and a wrong extraction cannot be traced back to the payload that
    caused it.

    One JSON object per line, documents first, then files. Every row carries
    enough to go back to the live site AND back to the saved bytes, so a
    disagreement can be settled without re-crawling.
    """
    rows: list[dict] = []
    for doc in documents:
        meta = doc.get("meta") or {}
        rows.append({
            "kind": "document",
            "doc_id": doc["doc_id"],
            "title": doc.get("title"),
            "live_url": doc.get("canonical_url"),
            "origin": meta.get("origin", "unrecorded"),
            "source": meta.get("source"),
            "section": meta.get("section"),
            "portion": meta.get("portion"),
            "owner": meta.get("owner"),
            "fetched_at": doc.get("fetched_at"),
            "content_path": doc.get("html_path"),
            "raw_payload": ("_meta/api_dump.json" if meta.get("source") == "api"
                            else doc.get("html_path")),
        })

    # A PDF is not "from" one page. The same circular is linked from a notice
    # index, a department page and sometimes a profile, and dropping all but the
    # last would misattribute it. `linked_from` is a list for that reason.
    for url in sorted(found_files):
        record = found_files[url]
        rows.append({
            "kind": "file",
            "file_url": url,
            "document_type": record.get("document_type"),
            "linked_from": record.get("linked_from", []),
            "local": record.get("local"),
            "title": record.get("title"),
        })

    path = out / "_meta" / "provenance.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + chr(10))
    log.info("provenance: %d documents + %d files -> %s",
             len(documents), len(found_files), path.name)
    return path



def write_file_index(out: Path, documents: list[dict], found_files: dict) -> Path:
    """Rewrite `_files/index.json` so every PDF says which documents it came from.

    Stage 5 writes this file when it downloads, and what it records is what the
    downloader knows: the URL, the bytes, the local name, and a list of page
    URLs. That is not enough to answer the question somebody actually has while
    holding a PDF - "what is this, and which part of the site is it from?" - and
    answering it meant joining three files by hand.

    So the page URLs are resolved into the documents themselves, and the
    document's section, portion, owner and originating endpoint travel with
    them. `linked_from` is left exactly as it was, because things already read
    it; `sources` is the added, resolved form.

    A PDF is deliberately allowed several sources. The same circular is linked
    from a notice index, a department page and sometimes a profile, and picking
    one would be inventing a relationship the site does not have.

    Runs offline off the shards, so the index can be rebuilt after a metadata
    change without re-downloading 285 PDFs.
    """
    index_path = out / "_files" / "index.json"
    existing: dict[str, dict] = {}
    if index_path.exists():
        try:
            rows = json.loads(index_path.read_text(encoding="utf-8"))
            existing = {r["url"]: r for r in rows if isinstance(r, dict) and r.get("url")}
        except (json.JSONDecodeError, OSError):
            log.warning("could not read %s; rebuilding it from scratch", index_path)

    by_url: dict[str, dict] = {}
    for doc in documents:
        meta = doc.get("meta") or {}
        by_url[doc.get("canonical_url")] = {
            "doc_id": doc["doc_id"],
            "title": doc.get("title"),
            "live_url": doc.get("canonical_url"),
            "section": meta.get("section"),
            "portion": meta.get("portion"),
            "owner": meta.get("owner"),
            "origin": meta.get("origin"),
        }

    rows = []
    for url in sorted(found_files):
        record = found_files[url]
        linked = record.get("linked_from", [])
        sources = [by_url[u] for u in linked if u in by_url]
        row = dict(existing.get(url, {}))
        row.update({
            "url": url,
            "document_type": record.get("document_type"),
            "linked_from": linked,
            "sources": sources,
            # A file linked only from a page that produced no document would
            # otherwise look unattached. Saying so is better than an empty list
            # that reads like a bug.
            "unresolved_links": [u for u in linked if u not in by_url],
            "downloaded": bool(row.get("local")),
        })
        rows.append(row)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    resolved = sum(1 for r in rows if r["sources"])
    _write_files_readme(index_path.parent, rows, resolved)
    log.info("file index: %d files, %d resolved to a document, %d downloaded",
             len(rows), resolved, sum(1 for r in rows if r["downloaded"]))
    return index_path


def _write_files_readme(files_dir: Path, rows: list[dict], resolved: int) -> None:
    """A note beside index.json saying which copy of it is authoritative.

    The PDFs are also kept on Google Drive, and a copy of the index goes with
    them. Two copies of a file that `--stage merge` rewrites every run will
    drift, and the failure is silent: restoring the older one strips `sources`
    from every entry and nothing errors.

    So the file states, next to itself, that the repository copy wins and when
    this one was generated. It travels to Drive with the PDFs, which is where
    somebody about to restore the wrong thing will be looking.
    """
    nl = chr(10)
    downloaded = sum(1 for r in rows if r["downloaded"])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# `_files/` - the downloaded PDFs and their index",
        "",
        "Generated by `--stage merge` on " + stamp + ".",
        "",
        "| | |",
        "|---|---|",
        "| Files known | " + str(len(rows)) + " |",
        "| Downloaded here | " + str(downloaded) + " |",
        "| Resolved to a document | " + str(resolved) + " |",
        "",
        "## Which copy of `index.json` is authoritative",
        "",
        "**The one in the git repository, at `engine/corpus/cuet/_files/`.**",
        "",
        "A copy is kept on Google Drive beside the PDFs. That copy is a mirror",
        "and goes stale the moment anybody runs `--stage merge`, because merge",
        "rewrites the index in full.",
        "",
        "Restoring from Drive means copying `*.pdf` only. Do not sync the folder",
        "wholesale: an older `index.json` landing on top of the repo copy removes",
        "the `sources` mapping from every entry, and nothing fails to tell you.",
        "Check the date above against the repo copy before restoring anything.",
        "",
        "Whoever changes the index should re-upload it and this note together, so",
        "the date on Drive always describes the file sitting beside it.",
    ]
    (files_dir / "README.md").write_text(nl.join(lines) + nl, encoding="utf-8")




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
    write_provenance(out, ordered_docs, found_files)
    write_file_index(out, ordered_docs, found_files)
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
