"""Parsers behind one interface: bytes -> text.

HTML always goes through BeautifulSoup. The `parser` setting really only picks
the **PDF** engine, because HTML parsing is a solved problem here — the hard
part of a web page is knowing which div is a cookie banner, which is a per-site
selector question, not a parsing one.

Build `BuiltinParser` first so the pipeline runs end to end, then add
`PdfPlumberParser` and compare the two on real PDFs.

TEAM B OWNS THIS FILE.

The three options
-----------------
builtin      pypdf. ~10 ms/page, ~15 MB resident, zero extra dependencies.
             Flattens tables into whitespace-separated runs.

pdfplumber   RECOMMENDED. pdfminer.six under the hood. ~100 ms/page, ~60 MB.
             Recovers ruled tables as real grids and keeps reading order.
             `uv add pdfplumber`

docling      IBM's converter: layout model + table model + OCR. Best output of
             the three, and it costs ~106 packages including torch and the CUDA
             stack, several GB on disk, 2-4 GB of RAM, and seconds per page on
             CPU. On an 8 GB laptop with no GPU it is the wrong tool. It is
             wired in for whoever later has a real machine, and it is the only
             option that handles SCANNED PDFs.

Choosing between them is an empirical question about YOUR sites' PDFs, not a
matter of taste. Extraction is a separate stage precisely so this is free:

    engine extract --run <run> --out builtin.jsonl    --config configs/extract.builtin.yaml
    engine extract --run <run> --out pdfplumber.jsonl --config configs/extract.pdfplumber.yaml

Then read both and let Team C's eval scores settle it.

"""

from __future__ import annotations

import logging
from typing import Protocol

from engine.knowledge.extraction import Extracted, SiteSelectors

log = logging.getLogger(__name__)


class Parser(Protocol):
    """Every parser satisfies this. Nothing above cares which one it got."""

    name: str

    def parse_html(self, html: str, url: str, selectors: SiteSelectors) -> Extracted: ...
    def parse_pdf(self, content: bytes) -> str: ...


class BuiltinParser:
    """BeautifulSoup for HTML, pypdf for PDFs. No network, no models.

    Build this one first — it is what CI runs and what lets the whole team work
    with no API key and no extra install.
    """

    name = "builtin"

    def parse_html(self, html: str, url: str, selectors: SiteSelectors) -> Extracted:
        """Delegate to extraction.extract."""
        raise NotImplementedError

    def parse_pdf(self, content: bytes) -> str:
        """Delegate to pdf.extract_pdf_text."""
        raise NotImplementedError


class PdfPlumberParser:
    """BeautifulSoup for HTML, pdfplumber for PDFs. The recommended choice.

    HTML still goes through the builtin path: the breadcrumb, the title and the
    per-site `drop` selectors are HTML-specific problems already solved in
    extraction.py, and routing HTML through a document converter throws all
    three away.

    Import pdfplumber lazily and raise a clear "run: uv add pdfplumber"
    if it is missing — the package is optional on purpose.
    """

    name = "pdfplumber"

    def __init__(self, max_pages: int = 200):
        raise NotImplementedError

    def parse_html(self, html: str, url: str, selectors: SiteSelectors) -> Extracted:
        raise NotImplementedError

    def parse_pdf(self, content: bytes) -> str:
        """Text with tables rendered as markdown, in reading order.

        Three things that matter, in order of how badly they bite:

        1. MEMORY. pdfplumber caches every character object per page. Call
           `page.flush_cache()` after each page, in a `finally`. Measured on a
           300-page table-heavy PDF: 366 MB without it, 67 MB with it. On an
           8 GB laptop that is the difference between working and swapping.

        2. READING ORDER. Do not extract all the prose and then append all the
           tables — a table's meaning lives in the sentence immediately above
           it, and the chunker can only use what is adjacent. Walk the page top
           to bottom: for each table (sorted by bbox top), emit the prose above
           it via `page.crop(...)`, then the table via `rows_to_markdown`, then
           continue below it.

        3. FALLING BACK. A corrupt file, or one with no text layer, must return
           "" or defer to pypdf — never raise. One bad PDF must not fail an
           extract over a whole site.
        """
        raise NotImplementedError


class DoclingParser:
    """Layout-aware conversion via docling. Requires the `docling` extra.

    Only worth building if your sites turn out to have scanned or genuinely
    complex PDFs, and only if someone has a machine that can run it. Check that
    around day 8 with real PDFs in hand — not on day 2.

    Like PdfPlumberParser, HTML delegates to the builtin path. Fall back to
    pypdf for any single document docling cannot handle.
    """

    name = "docling"

    def __init__(self):
        raise NotImplementedError

    def parse_html(self, html: str, url: str, selectors: SiteSelectors) -> Extracted:
        raise NotImplementedError

    def parse_pdf(self, content: bytes) -> str:
        raise NotImplementedError


def build_parser(name: str = "builtin") -> Parser:
    """Map a config string to a parser.

    An unknown name must raise ValueError listing what IS supported — a typo in
    a config should tell you the options, not fail with a KeyError three frames
    down. The message should name all three: builtin, pdfplumber, docling.
    """
    raise NotImplementedError
