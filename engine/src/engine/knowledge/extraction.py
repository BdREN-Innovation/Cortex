"""Saved HTML -> title, clean prose, tables, breadcrumb."""

from __future__ import annotations

from dataclasses import dataclass, field
from bs4 import BeautifulSoup, NavigableString, Tag

STRIP_TAGS = ["script", "style", "noscript", "template", "svg", "iframe", "form"]
CHROME_TAGS = ["nav", "header", "footer", "aside"]
MAIN_SELECTORS = ["main", "article", "[role=main]", "#content", ".content", "#main"]


@dataclass
class SiteSelectors:
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
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = []
    for r in rows:
        cells = [str(c).replace("|", "\\|").replace("\n", " ").strip() for c in r]
        cells += [""] * (width - len(cells))
        norm.append(cells)
    header, *body = norm
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def table_to_markdown(table: Tag) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells: list[str] = []
        for cell in tr.find_all(["td", "th"]):
            text = cell.get_text(" ", strip=True)
            colspan = int(cell.get("colspan", 1) or 1)
            cells.extend([text] * colspan)  # repeat merged cell across columns
        if cells:
            rows.append(cells)
    return rows_to_markdown(rows)


def _extract_breadcrumb(soup: BeautifulSoup, override_selector: str) -> list[str]:
    candidates = [override_selector] if override_selector else []
    candidates += ["nav[aria-label='breadcrumb']", ".breadcrumb", ".breadcrumbs", ".crumbs"]
    for sel in candidates:
        if not sel:
            continue
        el = soup.select_one(sel)
        if el:
            crumbs = [a.get_text(strip=True) for a in el.find_all("a")]
            crumbs = [c for c in crumbs if c]
            if crumbs:
                return crumbs
    return []


def _collapse_blank_lines(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract(html: str, url: str, selectors: SiteSelectors | None = None) -> Extracted:
    selectors = selectors or SiteSelectors()
    soup = BeautifulSoup(html, "html.parser")

    # Site-specific junk removal must happen before anything else reads the doc.
    for sel in selectors.drop:
        for el in soup.select(sel):
            el.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""

    meta = {}
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        meta["description"] = desc["content"].strip()

    section_path = _extract_breadcrumb(soup, selectors.breadcrumb)

    for tag_name in STRIP_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    main_el = soup.select_one(selectors.main) if selectors.main else None
    if main_el is None:
        for sel in MAIN_SELECTORS:
            main_el = soup.select_one(sel)
            if main_el:
                break

    if main_el is not None:
        for tag_name in CHROME_TAGS:
            for el in main_el.find_all(tag_name):
                el.decompose()
        root = main_el
    else:
        # No <main>/<article> found — don't strip chrome, or a simple page
        # could get blanked out entirely.
        root = soup.body or soup

    tables: list[dict] = []
    for i, table in enumerate(root.find_all("table")):
        md = table_to_markdown(table)
        if md:
            tables.append({"index": i, "markdown": md})
            table.replace_with(NavigableString("\n" + md + "\n"))

    for img in root.find_all("img"):
        alt = (img.get("alt") or "").strip()
        if len(alt.split()) >= 3:
            img.replace_with(NavigableString(alt))
        else:
            img.decompose()

    text = _collapse_blank_lines(root.get_text(separator="\n", strip=True))

    return Extracted(title=title, text=text, section_path=section_path, meta=meta, tables=tables)