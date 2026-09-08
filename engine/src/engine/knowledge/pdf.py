"""Linked files -> text.

A PDF on a site is usually the densest thing on it — the price list, the terms,
the manual. Parsing it into a normal `CleanDocument` means the rest of the
pipeline chunks, embeds and cites it with no new code: to everything downstream
it is just another row.

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
* Which library reads the PDF? See `parsers.py` — this is where that choice
  becomes real. Look at the PDFs your sites actually serve first.
* A PDF rarely carries a usable title. Where do you get one from?
* How many pages do you read? One 300-page manual should not dominate an index
  built from 200 web pages.
* What do you do with a file that is corrupt, encrypted, or a scan with no text
  layer at all? None of those are errors in the "crash the run" sense.
* PDF text arrives hard-wrapped, with headers and footers repeated on every
  page. How much of that do you clean up, and how much is the chunker's
  problem?

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

    Never let a remote URL choose a path on your disk. "../../etc/passwd" must
    not survive this function, and neither should a 400-character filename or
    one full of characters your filesystem rejects.
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

    Some files will be corrupt, encrypted, or scans with no text layer at all.
    None of those are errors in the "crash the run" sense — one bad download
    must not fail an extract over a whole site.
    """
    raise NotImplementedError
