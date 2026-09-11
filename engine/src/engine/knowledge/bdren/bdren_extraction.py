"""bdren.net.bd HTML -> clean text -> documents.jsonl.

Self-contained: everything needed to turn a bdren crawl run into
documents.jsonl lives in this one file. It does not import from or modify
`extraction.py` / `documents.py` (those stay untouched, in case Team B builds
their own version there separately).

Run directly:
    uv run python -m engine.knowledge.bdren.bdren_extraction data/sites/bdren/<run>

Owner: Mifta
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from engine.contracts.jsonio import read_jsonl, write_jsonl

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction: saved HTML -> title, clean prose, tables, breadcrumb.
# ---------------------------------------------------------------------------

STRIP_TAGS = ["script", "style", "noscript", "template", "svg", "iframe", "form"]
CHROME_TAGS = ["nav", "header", "footer", "aside"]
MAIN_SELECTORS = ["main", "article", "[role=main]", "#content", ".content", "#main"]
_MIN_MEANINGFUL_ALT_LENGTH = 25

_WHITESPACE_RUN = re.compile(r"[ \t\f\v]+")
_BLANK_LINE_RUN = re.compile(r"\n{3,}")


@dataclass
class SiteSelectors:
    """bdren-specific overrides. Empty by default — generic fallbacks worked
    fine in testing. Fill in only if a specific bdren page type extracts badly."""

    main: str = ""
    drop: list[str] = field(default_factory=list)
    breadcrumb: str = ""


@dataclass
class Extracted:
    title: str
    text: str
    section_path: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    tables: list[dict] = field(default_factory=list)


def rows_to_markdown(rows: list[list[str]]) -> str:
    """Render a grid of cells as a markdown table."""
    if not rows:
        return ""

    def _escape_cell(cell: str) -> str:
        cell = (cell or "").replace("|", "\\|")
        cell = re.sub(r"\s+", " ", cell).strip()
        return cell

    width = max(len(row) for row in rows)
    normalized = [
        [_escape_cell(cell) for cell in row] + [""] * (width - len(row))
        for row in rows
    ]

    header, *body = normalized
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

def table_to_markdown(table) -> str:
    """Render one HTML table element as markdown, handling rowspan/colspan."""
    if table is None:
        return ""

    grid: list[list[str]] = []

    def _ensure_row(r: int) -> None:
        while len(grid) <= r:
            grid.append([])

    def _ensure_col(row: list[str], c: int) -> None:
        while len(row) <= c:
            row.append(None)

    for r, tr in enumerate(table.find_all("tr")):
        _ensure_row(r)
        c = 0
        for cell in tr.find_all(["th", "td"], recursive=False):
            _ensure_col(grid[r], c)
            while grid[r][c] is not None:
                c += 1
                _ensure_col(grid[r], c)

            text = cell.get_text(" ", strip=True)
            rowspan = int(cell.get("rowspan", 1) or 1)
            colspan = int(cell.get("colspan", 1) or 1)

            for dr in range(rowspan):
                _ensure_row(r + dr)
                for dc in range(colspan):
                    _ensure_col(grid[r + dr], c + dc)
                    grid[r + dr][c + dc] = text

            c += colspan

    rows = [[cell or "" for cell in row] for row in grid if row]
    return rows_to_markdown(rows)


def _find_breadcrumb(soup: BeautifulSoup, selector: str) -> list[str]:
    node = None
    if selector:
        node = soup.select_one(selector)
    if node is None:
        node = (
            soup.select_one('[class*="breadcrumb" i]')
            or soup.select_one('[id*="breadcrumb" i]')
            or soup.select_one('nav[aria-label*="breadcrumb" i]')
        )
    if node is None:
        return []

    parts = [a.get_text(" ", strip=True) for a in node.find_all("a")]
    parts = [p for p in parts if p]
    if not parts:
        raw = node.get_text(" ", strip=True)
        parts = [p.strip() for p in re.split(r"[/>»]", raw) if p.strip()]
    return parts


def _find_main(soup: BeautifulSoup, selectors: SiteSelectors) -> Tag:
    if selectors.main:
        found = soup.select_one(selectors.main)
        if found is not None:
            return found
    for sel in MAIN_SELECTORS:
        found = soup.select_one(sel)
        if found is not None:
            return found
    return soup.body or soup


def _alt_text_for(img: Tag) -> str:
    alt = (img.get("alt") or "").strip()
    return alt if len(alt) >= _MIN_MEANINGFUL_ALT_LENGTH else ""


def _clean_whitespace(text: str) -> str:
    text = _WHITESPACE_RUN.sub(" ", text)
    text = _BLANK_LINE_RUN.sub("\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def extract(html: str, url: str, selectors: SiteSelectors | None = None) -> Extracted:
    """Read saved HTML for meaning."""
    selectors = selectors or SiteSelectors()
    soup = BeautifulSoup(html or "", "html.parser")

    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for sel in selectors.drop:
        for tag in soup.select(sel):
            tag.decompose()

    h1 = soup.find("h1")
    if h1 is not None and h1.get_text(strip=True):
        title = h1.get_text(" ", strip=True)
    elif soup.title is not None and soup.title.get_text(strip=True):
        title = soup.title.get_text(" ", strip=True)
    else:
        title = ""

    section_path = _find_breadcrumb(soup, selectors.breadcrumb)

    meta: dict = {}
    desc = soup.find("meta", attrs={"name": "description"})
    if desc is not None and desc.get("content"):
        meta["description"] = desc["content"].strip()
    lang = soup.html.get("lang") if soup.html else None
    if lang:
        meta["lang"] = lang.strip()

    main = _find_main(soup, selectors)

    for tag_name in CHROME_TAGS:
        for tag in main.find_all(tag_name):
            tag.decompose()

    tables: list[dict] = []
    for idx, table_tag in enumerate(main.find_all("table")):
        md = table_to_markdown(table_tag)
        if not md:
            continue
        tables.append({"index": idx, "markdown": md})
        table_tag.replace_with(NavigableString(f"\n\n{md}\n\n"))

    for img in main.find_all("img"):
        alt = _alt_text_for(img)
        img.replace_with(NavigableString(f" {alt} " if alt else " "))

    raw_text = main.get_text("\n")
    text = _clean_whitespace(raw_text)

    return Extracted(title=title, text=text, section_path=section_path, meta=meta, tables=tables)

# ---------------------------------------------------------------------------
# Documents: pages.jsonl -> documents.jsonl (bdren-specific run)
# ---------------------------------------------------------------------------


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _make_doc_id(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]


# bdren.net.bd-specific overrides. Empty for now — generic fallbacks
# (main/article/#content, then <body>) handled the site fine in testing.
BDREN_SELECTORS = SiteSelectors(main="", drop=[], breadcrumb="")
MIN_TEXT_CHARS = 200
SAVE_TABLES = True


def extract_bdren_run(run_dir: str | Path, out_path: str | Path | None = None) -> Path:
    """Read a bdren crawl run and write documents.jsonl beside it.

    Example:
        extract_bdren_run("data/sites/bdren/bdren-20260911T042956Z")
    """
    run_dir = Path(run_dir)
    out_path = Path(out_path) if out_path else run_dir / "documents.jsonl"
    pages_path = run_dir / "pages.jsonl"

    documents: list[dict] = []
    seen_hashes: dict[str, str] = {}
    counts = {"pages": 0, "pdfs_skipped": 0, "too_short": 0, "duplicate": 0, "errors": 0}

    for page in read_jsonl(pages_path):
        counts["pages"] += 1

        content_type = (page.get("content_type") or "").lower()
        content_path = page.get("content_path", "")
        canonical_url = page.get("canonical_url", "")
        is_pdf = "pdf" in content_type or content_path.lower().endswith(".pdf")

        if is_pdf:
            # No PDF text parser exists yet in this project. Skipped and
            # counted rather than emitted as a fake/empty document.
            counts["pdfs_skipped"] += 1
            log.info("Skipped PDF (no parser yet): %s", canonical_url)
            continue

        status = page.get("status", 200)
        if status < 200 or status >= 300:
            counts["errors"] += 1
            log.info("Dropped (HTTP %s, not a success): %s", status, canonical_url)
            continue

        content_file = run_dir / content_path
        try:
            html = content_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            counts["errors"] += 1
            log.warning("Could not read %s: %s", content_file, exc)
            continue

        try:
            result = extract(html, canonical_url, BDREN_SELECTORS)
        except Exception:  # noqa: BLE001 - one bad page must not kill the whole run
            counts["errors"] += 1
            log.exception("Extraction failed for %s", canonical_url)
            continue

        if len(result.text.strip()) < MIN_TEXT_CHARS:
            counts["too_short"] += 1
            log.info("Dropped (too short): %s", canonical_url)
            continue

        text_hash = _content_hash(result.text)
        if text_hash in seen_hashes:
            counts["duplicate"] += 1
            log.info("Dropped (duplicate of %s): %s", seen_hashes[text_hash], canonical_url)
            continue
        seen_hashes[text_hash] = canonical_url

        assets: list[dict] = []
        if SAVE_TABLES:
            for table in result.tables:
                page_id = page.get("page_id", text_hash[:16])
                table_path = run_dir / "tables" / f"{page_id}-{table['index']}.md"
                table_path.parent.mkdir(parents=True, exist_ok=True)
                table_path.write_text(table["markdown"], encoding="utf-8")
                assets.append(
                    {
                        "kind": "table",
                        "path": str(table_path.relative_to(run_dir)),
                        "source_url": canonical_url,
                        "ordinal": table["index"],
                        "alt": "",
                        "meta": {},
                    }
                )

        documents.append(
            {
                "doc_id": _make_doc_id(canonical_url),
                "source_url": page.get("url", canonical_url),
                "canonical_url": canonical_url,
                "title": result.title,
                "text": result.text,
                "content_hash": text_hash,
                "fetched_at": page.get("fetched_at", ""),
                "section_path": result.section_path,
                "html_path": content_path,
                "lang": result.meta.get("lang", "en"),
                "meta": result.meta,
                "doc_type": "page",
                "assets": assets,
            }
        )

    write_jsonl(out_path, documents)

    log.info(
        "extract_bdren_run: documents=%d pdfs_skipped=%d too_short=%d duplicate=%d errors=%d run=%s",
        len(documents),
        counts["pdfs_skipped"],
        counts["too_short"],
        counts["duplicate"],
        counts["errors"],
        run_dir,
    )
    print(
        f"documents={len(documents)} pdfs_skipped={counts['pdfs_skipped']} "
        f"too_short={counts['too_short']} duplicate={counts['duplicate']} errors={counts['errors']}"
    )

    return out_path


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s\t%(message)s")

    if len(sys.argv) != 2:
        print("Usage: uv run python -m engine.knowledge.bdren.bdren_extraction <run_dir>")
        sys.exit(1)

    output = extract_bdren_run(sys.argv[1])
    print(f"documents.jsonl written to: {output}")