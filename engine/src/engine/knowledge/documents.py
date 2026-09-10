"""pages.jsonl -> documents.jsonl.

Team B's first stage, and the boundary with Team A. It reads bytes that were
already captured, so it runs offline, in seconds, as many times as you like.

TEAM B OWNS THIS FILE.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from engine.knowledge.extraction import extract, rows_to_markdown, SiteSelectors
from engine.knowledge.parsers import parse_document

# TEMPORARY — swap this for the real Team A contracts once it lands:
# from engine.contracts import CrawledPage, CleanDocument
from scratch.contracts_stub import CrawledPage, CleanDocument

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


def _doc_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


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
    kind = getattr(page, "content_type", None)
    return kind == "pdf" or str(page.content_path).lower().endswith(".pdf")


def _process_html(run_dir: Path, page: CrawledPage, config: ExtractConfig) -> CleanDocument | None:
    html_path = run_dir / page.content_path
    html = html_path.read_text(encoding="utf-8", errors="replace")
    result = extract(html, url=page.url, selectors=config.selectors)

    if len(result.text.strip()) < config.min_text_chars:
        log.info("drop thin page: %s (%d chars)", page.url, len(result.text.strip()))
        return None

    return CleanDocument(
        doc_id=_doc_id(page.url),
        url=page.url,
        doc_type="page",
        title=result.title,
        text=result.text,
        section_path=result.section_path,
        tables=result.tables,
        source_path=str(page.content_path),
        meta=result.meta,
    )


def _process_pdf(run_dir: Path, page: CrawledPage, config: ExtractConfig) -> CleanDocument | None:
    pdf_path = run_dir / page.content_path
    parsed = parse_document(str(pdf_path))

    if parsed["empty"] or len(parsed["text"].strip()) < config.min_text_chars:
        log.info("drop thin/empty pdf: %s", page.url)
        return None

    tables = [
        {"index": i, "markdown": rows_to_markdown(t)}
        for i, t in enumerate(parsed.get("tables", []))
        if t
    ]

    section_path = list(getattr(page, "linked_from_breadcrumb", []) or [])
    if not section_path and getattr(page, "linked_from", None):
        section_path = [page.linked_from]

    return CleanDocument(
        doc_id=_doc_id(page.url),
        url=page.url,
        doc_type="pdf",
        title=Path(page.content_path).stem,
        text=parsed["text"],
        section_path=section_path,
        tables=tables,
        source_path=str(page.content_path),
        meta={
            "ocr_used": parsed.get("ocr_used", False),
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
    documents: list[CleanDocument] = []
    n_pdf = n_dropped_thin = n_dropped_dup = n_errors = 0

    for page in pages:
        norm = _normalize_url(page.url)
        if norm in seen_urls:
            n_dropped_dup += 1
            continue

        try:
            doc = _process_pdf(run_dir, page, config) if _is_pdf(page) else _process_html(run_dir, page, config)
        except Exception:
            log.exception("failed to extract %s", page.url)
            n_errors += 1
            continue

        if doc is None:
            n_dropped_thin += 1
            continue

        if _is_pdf(page):
            n_pdf += 1

        doc.validate()
        seen_urls.add(norm)
        documents.append(doc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")

    log.info(
        "extract_documents: %d docs (%d pdf) | dropped: %d thin, %d dup | %d errors -> %s",
        len(documents), n_pdf, n_dropped_thin, n_dropped_dup, n_errors, out_path,
    )
    return out_path