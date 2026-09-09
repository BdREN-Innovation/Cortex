"""Stage 2: turn the API payloads into documents.

After the 2026-09-08 revision this is where most of the corpus comes from —
roughly 530 documents from about 45 requests, with no browser. Spec §6.8.

Every source writes the same three-file shape, so a consumer cannot tell a
JSON-derived document from a browser-captured one except by reading `source`.
That uniformity is deliberate: downstream code should not branch on provenance.

**This module no longer holds the builders.** They live one module per portion
under `builders/`, registered in `builders/__init__.py`, so that four people can
each own their slice of the site without editing a file the others also edit.
What is left here is the part every portion shares: writing a document to disk,
and writing the shard that `--stage merge` later assembles into a corpus.

A run writes ONLY its own shard. The corpus-wide `documents.jsonl`,
`pages.jsonl` and `manifest.json` are produced by `merge.py` and are generated
files — never committed, never hand-edited. That is what stops two people who
ran different portions from conflicting on every pull request.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from engine.contracts.documents import CleanDocument, content_hash

from . import config
from .builders import builders_for, portion_names
from .builders.base import (Document, Stage2Result, _clean_html, _headline_body,
                            _now, harvest)
from .markdown import to_markdown
from .paths import canonical, page_id, safe_name

log = logging.getLogger(__name__)

# Re-exported so that `capture.py` and anything else that already speaks in
# these terms keeps working. The definitions live in builders/base.py.
__all__ = ["Document", "Stage2Result", "harvest", "write_document",
           "to_clean_document", "run", "SHARDS"]

_ = (_clean_html, _headline_body)   # re-exported for builders' convenience

# Per-portion output. One file per portion, one owner per file, so two people
# running different portions never write the same path. `merge.py` reads them.
SHARDS = "_shards"


def write_document(doc: Document, out: Path,
                   fetched_at: str | None = None) -> dict:
    """Write the .html / .md / .json triple atomically. Spec §6.5, §7.3.

    Order is html, md, json — the JSON is the completion marker for
    resumability, so it goes last. Spec §7.1.

    `fetched_at` is when the bytes came off CUET's servers, which for an
    API-derived document is when the dump was taken, not when it was rebuilt
    from that dump. Browser captures pass nothing and get the current time,
    which for them is the same thing.
    """
    folder = out / doc.section / doc.group if doc.group else out / doc.section
    folder.mkdir(parents=True, exist_ok=True)

    doc_id = page_id(doc.key)
    # Slug from the PATH only. The key may carry synthetic query parameters
    # (see Document) and those belong in the id, not in the filename.
    slug = safe_name(
        doc.key.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "index",
        keep_extension=False,
    )
    stem = f"{slug}__{doc_id[:8]}"

    text = to_markdown(doc.html)
    html_path = folder / f"{stem}.html"
    md_path = folder / f"{stem}.md"
    json_path = folder / f"{stem}.json"

    # HTML as BYTES, not decoded text. A decoding mistake stays recoverable;
    # a mis-decoded save is only fixable by re-crawling. Spec §4.12.
    _atomic_write_bytes(html_path, doc.html.encode("utf-8"))
    _atomic_write_bytes(md_path, text.encode("utf-8"))

    meta = {
        "url": doc.url,
        "canonical_url": canonical(doc.url),
        "page_id": doc_id,
        "doc_key": doc.key,
        "section": doc.section,
        "group": doc.group,
        "section_path": doc.section_path,
        "title": doc.title,
        "source": doc.source,
        "status": 200,
        "fetched_at": fetched_at or _now(),
        "html_path": str(html_path.relative_to(out)).replace("\\", "/"),
        "markdown_path": str(md_path.relative_to(out)).replace("\\", "/"),
        "text_chars": len(text),
        "render_ok": True,
        "attempts": 1,
        "links_found": len(doc.files),
        "double_escaped": doc.double_escaped,
        "files": doc.files,
        **doc.extra,
    }
    _atomic_write_bytes(
        json_path, json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
    )
    meta["_text"] = text
    meta["_json_path"] = json_path
    return meta


def _atomic_write_bytes(dest: Path, payload: bytes) -> None:
    """Write via a .part file and rename. Spec §7.3.

    Without this, an interrupt mid-write leaves a truncated file that the resume
    check counts as complete, and the corruption stays invisible until something
    downstream fails.
    """
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(payload)
    tmp.replace(dest)


def to_clean_document(meta: dict) -> CleanDocument:
    """A CleanDocument row for API-derived content. Spec §12.1.

    Deliberate deviation, stated rather than slipped in: CrawledPage carries no
    text because HTML needs cleaning and that is Team B's job. API content
    arrives as prose with no navigation, banner or footer to strip, so the
    extraction step would have nothing to do.
    """
    text = meta["_text"]
    return CleanDocument(
        doc_id=meta["page_id"],
        source_url=meta["url"],
        canonical_url=meta["canonical_url"],
        title=meta["title"],
        text=text,
        content_hash=content_hash(text),
        fetched_at=meta["fetched_at"],
        section_path=meta["section_path"],
        html_path=meta["html_path"],
        lang="en",
        doc_type="page",
        meta={"source": meta["source"], "section": meta["section"]},
    )



def run(dump: dict, out: Path | None = None,
        portions: list[str] | None = None) -> Stage2Result:
    """Build and write one portion's documents, plus its shard.

    `portions` selects which slices of the site to build; `None` means all of
    them, which is what a single-person full run does. Naming a portion is what
    makes a four-person run safe: each person writes their own section folders
    and their own shard, and nothing else.

    What this does NOT write is the corpus-wide `documents.jsonl`,
    `pages.jsonl` or `manifest.json`. Those are `--stage merge`, because a file
    that every portion rewrites is a file every portion conflicts on.
    """
    out = out or config.OUT
    result = Stage2Result()

    # Stamped by `--stage discover`. A dump predating that field falls back to
    # the current time, which is the old behaviour and only affects old dumps.
    fetched_at = dump.get("_fetched_at") or _now()

    selected = portions or list(portion_names())
    log.info("content: building portion(s) %s", ", ".join(selected))

    for builder in builders_for(portions):
        before = len(result.documents)
        builder(dump, result)
        log.info("%-28s produced %4d documents", builder.__name__,
                 len(result.documents) - before)

    meta_dir = out / "_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for doc in result.documents:
        # A document whose HTML yields no text is not a document. This happens
        # for records that carry only a banner image, and for events whose
        # description is an empty <p>. Dropping them here beats writing a row
        # that fails CleanDocument.validate() downstream — and it is NOT the
        # thin-page filtering spec §4.4 forbids, because the raw payload is
        # still in _meta/api_dump.json and nothing has been discarded.
        if not to_markdown(doc.html).strip():
            log.info("skipping %s: no text after conversion", doc.key)
            result.warnings.append(f"empty_document:{doc.key}")
            continue
        rows.append(write_document(doc, out, fetched_at))

    write_shard(out, selected, rows, result)
    result.rows = rows
    log.info("content: %d documents across %d portion(s), "
             "%d files discovered, %d pages discovered",
             len(rows), len(selected), len(result.found_files),
             len(result.found_pages))
    return result


def write_shard(out: Path, portions: list[str], rows: list[dict],
                result: Stage2Result) -> Path:
    """Everything one portion produced, in one file it alone owns.

    Named after the portions built rather than after the run, so re-running a
    portion overwrites its own shard instead of accumulating stale copies. A
    run of several portions writes one combined shard under a joined name; a
    four-person project runs one portion each and gets four files.

    `found_files` and `found_pages` ride along rather than going to the
    corpus-wide `_meta/found_files.json`, for the same reason the documents do:
    a whole-corpus file that four people rewrite is four people's merge
    conflict. `merge.py` unions them.
    """
    shard_dir = out / SHARDS
    shard_dir.mkdir(parents=True, exist_ok=True)
    name = "+".join(sorted(portions)) or "all"
    path = shard_dir / f"{name}.json"

    documents, pages = [], []
    for row in rows:
        clean = to_clean_document(row)
        problems = clean.validate()
        if problems:
            log.warning("CleanDocument %s invalid: %s", clean.doc_id, problems)
            result.warnings.append(f"invalid_document:{clean.doc_id}")
            continue
        documents.append(clean.__dict__)
        pages.append(_crawled_page_row(row))

    # `captured_at`, not `built_at`. A wall-clock build time changes on every
    # run, so re-running a portion that produced identical documents still
    # rewrote its shard and showed up as a diff saying nothing. Deriving it from
    # the content means an unchanged rebuild is byte-identical, which is the
    # same property the documents themselves have.
    captured = max((row.get("fetched_at") or "" for row in rows), default="") or _now()

    payload = {
        "portions": sorted(portions),
        "captured_at": captured,
        "documents": documents,
        "pages": pages,
        "found_files": list(result.found_files.values()),
        "found_pages": sorted(result.found_pages),
        "warnings": result.warnings,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               default=str, sort_keys=False), encoding="utf-8")
    log.info("shard %s: %d documents, %d pages, %d files, %d warnings",
             path.name, len(documents), len(pages),
             len(result.found_files), len(result.warnings))
    return path


def _crawled_page_row(row: dict) -> dict:
    """The CrawledPage fields, kept in the shard so merge needs no re-derivation."""
    return {
        "page_id": row["page_id"],
        "url": row["url"],
        "canonical_url": row["canonical_url"],
        "status": row.get("status", 200),
        "content_path": row["html_path"],
        "fetched_at": row["fetched_at"],
        "document_links": [f["url"] for f in row.get("files", [])],
        "source": row.get("source", "api"),
        "section": row.get("section", ""),
        "section_path": row.get("section_path", []),
    }
