"""pages.jsonl -> documents.jsonl.

Team B's first stage, and the boundary with Team A. It reads bytes that were
already captured, so it runs offline, in seconds, as many times as you like.

TEAM B OWNS THIS FILE.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from engine.contracts import documents
from engine.knowledge.extraction import extract, rows_to_markdown, SiteSelectors
from engine.knowledge.parsers import parse_document
from engine.contracts.documents import (
    Asset,
    CleanDocument,
    CrawledPage,
    content_hash,
    make_doc_id,
)

log = logging.getLogger(__name__)


@dataclass
class ExtractConfig:
    min_text_chars: int = 200
    save_tables: bool = True
    parser: str = ""
    selectors: SiteSelectors = field(default_factory=SiteSelectors)

    @classmethod
    def from_dict(cls, payload: dict) -> "ExtractConfig":
        raw_sel = payload.get("selectors") or {}
        selectors = SiteSelectors(
            main=raw_sel.get("main", ""),
            drop=list(raw_sel.get("drop", [])),
            breadcrumb=raw_sel.get("breadcrumb", ""),
        )
        return cls(
            min_text_chars=payload.get("min_text_chars", 200),
            save_tables=payload.get("save_tables", True),
            parser=payload.get("parser", ""),
            selectors=selectors,
        )


def _normalize_url(url: str) -> str:
    """Collapse the '/' vs '/index.html' duplicate case."""
    for suffix in ("/index.html", "/index.htm"):
        if url.endswith(suffix):
            return url[: -len(suffix)] or "/"
    return url.rstrip("/") or "/"


def _load_pages(run_dir: Path) -> list[CrawledPage]:
    pages = []
    with (run_dir / "pages.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pages.append(CrawledPage.from_dict(json.loads(line)))
    return pages


def _is_pdf(page: CrawledPage) -> bool:
    return page.content_type == "pdf" or str(page.content_path).lower().endswith(".pdf")


def _is_docx(page: CrawledPage) -> bool:
    return page.content_type == "docx" or str(page.content_path).lower().endswith(".docx")


def _tables_to_assets(
    run_dir: Path, page: CrawledPage, raw_tables: list, config: ExtractConfig
) -> list[dict]:
    """Write each table to disk as a markdown file and return Asset dicts.

    The table text itself already lives inline in the page prose (per the
    ASSET_KINDS docstring in contracts.documents) — these are the eyeball
    copies for provenance/inspection, not a second source of chunkable text.
    """
    if not config.save_tables or not raw_tables:
        return []

    assets: list[dict] = []
    table_dir = run_dir / "assets" / "tables"
    # TODO: confirm this output layout with Team A / whoever reads assets
    # later (indexer? a debug UI?) — picked a plausible convention
    # (assets/tables/<doc-safe-name>-<n>.md) but nothing upstream specifies one.
    table_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(page.content_path).stem or "table"

    for i, table in enumerate(raw_tables):
        if not table:
            continue
        md = rows_to_markdown(table)
        out_path = table_dir / f"{safe_stem}-{i}.md"
        out_path.write_text(md, encoding="utf-8")
        assets.append(
            Asset(
                kind="table",
                path=str(out_path.relative_to(run_dir)),
                source_url=page.url,
                ordinal=i,
            ).to_dict()
        )
    return assets


def _section_path_for(page: CrawledPage) -> list[str]:
    """Best-effort breadcrumb for a linked file (PDF/docx).

    The stub's CrawledPage carried `linked_from_breadcrumb` (a full trail);
    the real contract only carries `parent_url` (a single URL, not a
    breadcrumb of titles). This is a real information loss, not a stylistic
    change — TODO: raise with Team A whether the crawler can still supply a
    title-breadcrumb, or whether Team C's eval harness should be told to
    expect single-element section_paths for pdf/docx rows for now.
    """
    if page.parent_url:
        return [page.parent_url]
    return []


def _process_html(run_dir: Path, page: CrawledPage, config: ExtractConfig) -> CleanDocument | None:
    html_path = run_dir / page.content_path
    html = html_path.read_text(encoding="utf-8", errors="replace")
    result = extract(html, url=page.url, selectors=config.selectors)

    if len(result.text.strip()) < config.min_text_chars:
        log.info("drop thin page: %s (%d chars)", page.url, len(result.text.strip()))
        return None

    text = result.text
    return CleanDocument(
        doc_id=make_doc_id(page.canonical_url),
        source_url=page.url,
        canonical_url=page.canonical_url,
        title=result.title,
        text=text,
        content_hash=content_hash(text),
        fetched_at=page.fetched_at,
        section_path=result.section_path,
        html_path=str(page.content_path),
        doc_type="page",
        assets=_tables_to_assets(run_dir, page, result.tables, config),
        meta=result.meta,
    )


def _process_pdf(run_dir: Path, page: CrawledPage, config: ExtractConfig) -> CleanDocument | None:
    pdf_path = run_dir / page.content_path
    parsed = parse_document(str(pdf_path))

    if parsed["empty"] or len(parsed["text"].strip()) < config.min_text_chars:
        log.info("drop thin/empty pdf: %s", page.url)
        return None

    text = parsed["text"]
    return CleanDocument(
        doc_id=make_doc_id(page.canonical_url),
        source_url=page.url,
        canonical_url=page.canonical_url,
        title=Path(page.content_path).stem,
        text=text,
        content_hash=content_hash(text),
        fetched_at=page.fetched_at,
        section_path=_section_path_for(page),
        doc_type="pdf",
        assets=_tables_to_assets(run_dir, page, parsed.get("tables", []), config), 
        meta={
            **page.meta,
            "source_url": page.url,
            "content_type": page.content_type,
            "ocr_used": parsed.get("ocr_used", False),
        },
    )


def _process_docx(run_dir: Path, page: CrawledPage, config: ExtractConfig) -> CleanDocument | None:
    docx_path = run_dir / page.content_path
    parsed = parse_document(str(docx_path))

    if parsed["empty"] or len(parsed["text"].strip()) < config.min_text_chars:
        log.info("drop thin/empty docx: %s", page.url)
        return None

    text = parsed["text"]
    return CleanDocument(
        doc_id=make_doc_id(page.canonical_url),
        source_url=page.url,
        canonical_url=page.canonical_url,
        title=Path(page.content_path).stem,
        text=text,
        content_hash=content_hash(text),
        fetched_at=page.fetched_at,
        section_path=_section_path_for(page),
        # TODO: DOC_TYPES is currently ("page", "pdf") only — no "docx" value
        # exists in the real contract. Mapping to "page" here so validate()
        # passes and it isn't silently dropped, but this is a guess, not a
        # decision — raise with Team A whether DOC_TYPES should grow a
        # "docx" entry, since collapsing it into "page" loses the distinction
        # documents.py currently tracks (n_pdf/n_docx counts below).
        doc_type="page",
        assets=_tables_to_assets(run_dir, page, parsed.get("tables", []), config), 
        meta={
            **page.meta,
            "source_url": page.url,
            "content_type": page.content_type,
        },
    )


def extract_documents(
    run_dir: str | Path,
    config: ExtractConfig | None = None,
    out_path: str | Path | None = None,
) -> Path:
    run_dir = Path(run_dir)
    config = config or ExtractConfig()
    out_path = Path(out_path) if out_path else run_dir / "documents.jsonl"

    pages = _load_pages(run_dir)

    seen_urls: set[str] = set()
    seen_content_hashes: set[str] = set()
    documents: list[CleanDocument] = []
    n_pdf = n_docx = n_dropped_thin = n_dropped_dup = n_errors = n_invalid = 0

    for page in pages:
        norm = _normalize_url(page.url)
        if norm in seen_urls:
            n_dropped_dup += 1
            continue

        try:
            if _is_pdf(page):
                doc = _process_pdf(run_dir, page, config)
            elif _is_docx(page):
                doc = _process_docx(run_dir, page, config)
            else:
                doc = _process_html(run_dir, page, config)
        except Exception:
            log.exception("failed to extract %s", page.url)
            n_errors += 1
            continue

        if doc is None:
            n_dropped_thin += 1
            continue

        problems = doc.validate()
        if problems:
            log.error("dropping invalid document %s: %s", page.url, "; ".join(problems))
            n_invalid += 1
            continue

        if _is_pdf(page):
            n_pdf += 1
        elif _is_docx(page):
            n_docx += 1

        if doc.content_hash in seen_content_hashes:
            n_dropped_dup += 1
            continue

        seen_content_hashes.add(doc.content_hash)
        seen_urls.add(norm)
        documents.append(doc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for doc in documents:
            f.write(json.dumps(doc.__dict__, default=str, ensure_ascii=False) + "\n")

    log.info(
        "extract_documents: %d docs (%d pdf, %d docx) | dropped: %d thin, %d dup, %d invalid | %d errors -> %s",
        len(documents), n_pdf, n_docx, n_dropped_thin, n_dropped_dup, n_invalid, n_errors, out_path,
    )
    return out_path