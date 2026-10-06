"""HTML to markdown, built on the standard library's html.parser.

No library is prescribed anywhere in this project, and this is a case where the
standard library genuinely suffices: the input is CMS-authored body HTML —
paragraphs, headings, lists, tables, links — not arbitrary web pages. A
dependency here would buy robustness against markup we never receive.

Two behaviours are requirements rather than preferences:

* **Alt text and <figcaption> are kept; image links are not emitted.** Alt text
  is prose sitting in HTML we already have and it belongs in the extracted text.
  An image URL does not, because nothing downstream may fetch it. Spec §4.6.
* **Tables become markdown grids** rather than being flattened, so that a seat
  table or a grading scale survives as a table. The undergraduate prospectus
  is largely tables. Spec §3.3.
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")

_BLOCK = {"p", "div", "section", "article", "header", "footer", "br",
          "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "figcaption"}
_SKIP = {"script", "style", "noscript", "svg", "iframe", "video", "audio"}
_HEADING = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}


class _Converter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip_depth = 0
        self._list_stack: list[str] = []
        self._href: str | None = None
        self._link_text: list[str] = []
        # Table state. Collected cell-by-cell so the grid can be emitted once
        # the row count is known.
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    # -- helpers -----------------------------------------------------------

    def _emit(self, text: str) -> None:
        if self._cell is not None:
            self._cell.append(text)
        elif self._href is not None:
            self._link_text.append(text)
        else:
            self.out.append(text)

    # -- tags --------------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in _SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "img":
            # Alt text only, and only when it reads like prose. A one-word
            # alt="logo" is chrome; a caption is a sentence about the page.
            alt = (attributes.get("alt") or "").strip()
            if len(alt.split()) >= 2:
                self._emit(f"{alt} ")
            return

        if tag == "a":
            self._href = attributes.get("href")
            self._link_text = []
            return

        if tag == "table":
            self._table = []
            return
        if tag == "tr" and self._table is not None:
            self._row = []
            return
        if tag in ("td", "th") and self._row is not None:
            self._cell = []
            return

        if tag in _HEADING:
            self._emit(f"\n\n{_HEADING[tag]} ")
        elif tag in ("ul", "ol"):
            self._list_stack.append(tag)
            self._emit("\n")
        elif tag == "li":
            depth = "  " * max(0, len(self._list_stack) - 1)
            marker = "-" if (self._list_stack or ["ul"])[-1] == "ul" else "1."
            self._emit(f"\n{depth}{marker} ")
        elif tag == "br":
            self._emit("\n")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag in _BLOCK:
            self._emit("\n\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag == "a" and self._href is not None:
            text = "".join(self._link_text).strip()
            href = self._href
            self._href, self._link_text = None, []
            if text and href and not href.startswith(("#", "javascript:")):
                self._emit(f"[{text}]({href})")
            elif text:
                self._emit(text)
            return

        if tag in ("td", "th") and self._cell is not None:
            cell = _WS.sub(" ", "".join(self._cell)).replace("\n", " ").strip()
            if self._row is not None:
                self._row.append(cell)
            self._cell = None
            return
        if tag == "tr" and self._row is not None:
            if self._table is not None:
                self._table.append(self._row)
            self._row = None
            return
        if tag == "table" and self._table is not None:
            self.out.append(_render_table(self._table))
            self._table = None
            return

        if tag in _HEADING:
            self._emit("\n\n")
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            self._emit("\n")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag in _BLOCK:
            self._emit("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        self._emit(_WS.sub(" ", data))


def _render_table(rows: list[list[str]]) -> str:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        # An all-blank table is the empty data grid from spec §2. Emitting
        # nothing is right; detecting it is render_failed()'s job, not ours.
        return "\n"
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head, body = rows[0], rows[1:]
    lines = ["", "| " + " | ".join(head) + " |",
             "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines) + "\n"


def to_markdown(html: str) -> str:
    """Convert body HTML to markdown text."""
    if not html:
        return ""
    converter = _Converter()
    converter.feed(html)
    converter.close()
    text = "".join(converter.out)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return _BLANKS.sub("\n\n", text).strip()


def html_to_text(html: str) -> str:
    """Plain text, for CleanDocument.text and for length checks."""
    return to_markdown(html)


def unescape_once(value: str) -> str:
    """Undo one layer of HTML escaping.

    `research_highlight` and `research_area` are stored already-escaped, so their
    values contain literal `&lt;p&gt;` rather than tags. Unescaping once yields
    HTML; not unescaping shows the reader raw tag text. Spec §3.3, §6.8.

    Deliberately once, not until stable: repeatedly unescaping would corrupt
    legitimate content that happens to contain `&amp;lt;`.
    """
    return unescape(value)
