"""Linked files -> text.

A PDF on a site is usually the densest thing on it — the price list, the terms,
the manual. Parsing it into a normal `CleanDocument` means the rest of the
pipeline chunks, embeds and cites it with no new code: to everything downstream
it is just another row.

TEAM B OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

pypdf         the baseline. Pure Python, ~10 ms a page, ~15 MB resident.
              PdfReader(BytesIO(content)).pages[i].extract_text().
              Gets the characters; flattens tables into whitespace.
pdfplumber    RECOMMENDED — see parsers.py. Also pure Python, ~100 ms a page,
              ~60 MB. Recovers ruled tables via page.find_tables().
urllib.parse  unquote + urlparse to turn a URL into a filename.
re            filename sanitising and whitespace tidying.

"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PARSABLE_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


def is_pdf(content_type: str, url: str) -> bool:
    """Is this a PDF?

    Trust the Content-Type when it is one of PARSABLE_CONTENT_TYPES, and fall
    back to the URL path ending in ".pdf". Plenty of servers send
    application/octet-stream for a perfectly good PDF.
    """
    raise NotImplementedError


def filename_for(url: str, fallback: str) -> str:
    """A safe on-disk name for a downloaded file.

    Take the last path segment, URL-decode it, replace anything that is not
    [A-Za-z0-9._-] with "_", and cap the length. Never let a URL choose a path:
    "../../etc/passwd" must not survive this function.
    """
    raise NotImplementedError


def title_from(url: str, text: str) -> str:
    """PDFs rarely carry a usable title, so derive one.

    Use the first line of the extracted text that looks like a title (long
    enough to be meaningful, short enough not to be a paragraph). Fall back to
    the filename with separators turned back into spaces.
    """
    raise NotImplementedError


def extract_pdf_text(content: bytes, max_pages: int = 200) -> str:
    """Return the text of a PDF, or "" if it cannot be read.

    Two failure modes that are NOT errors and must not raise:

      * A corrupt or unreadable file. Log a warning, return "". One bad
        download must not fail an extract over a whole site.
      * A scanned PDF. It is a stack of images with no text layer, so it yields
        nothing. The caller drops it exactly like a thin HTML page. Solving this
        needs OCR, which is out of scope — log it and move on.

    Cap at `max_pages`: one 300-page manual should not dominate the index.
    Tidy the output — PDF extraction leaves hard-wrapped lines and repeated
    blank runs whatever produced it.
    """
    raise NotImplementedError
