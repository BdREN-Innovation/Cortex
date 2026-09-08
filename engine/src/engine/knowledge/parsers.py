"""One interface, however many parsers you end up wanting.

HTML and PDF need different machinery, and you will probably want to try more
than one PDF library before you settle. This module exists so that swapping one
out is a config change rather than an edit to `documents.py`.

The Protocol is the structure. What sits behind it is yours.

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
* What parses HTML? What parses PDFs? Are they the same class or two?
* PDFs vary enormously — a clean single-column policy document, a multi-column
  report, a dense financial table, a scanned page that is really just an image.
  Look at the PDFs your sites actually serve before choosing. The answer for a
  government PDF library is not the answer for a SaaS pricing sheet.
* How much do you care about tables inside PDFs? A parser that recovers a ruled
  table as a grid, versus one that flattens it into loose numbers, changes what
  a chunk means. Some libraries do this; some do not.
* What happens to a scanned PDF with no text layer? Every text-only parser
  returns nothing. Is that acceptable, or does it need solving?
* What does a parser cost — install size, memory, seconds per page? You are on
  8 GB laptops with no GPU. Check before you commit to something.

How to decide
-------------
Not by reading opinions — including this file's. Extraction is a separate
stage precisely so running two parsers over the same crawl is free:

    engine extract --run <run> --config configs/extract.a.yaml --out a.jsonl
    engine extract --run <run> --config configs/extract.b.yaml --out b.jsonl

Diff the `text` fields, then let Team C's eval scores settle it. Whatever wins
is a fact about your corpus, not a preference. Write down what you compared and
why you chose what you chose — that argument is part of the deliverable.
"""

from __future__ import annotations

import logging
from typing import Protocol

from engine.knowledge.extraction import Extracted, SiteSelectors

log = logging.getLogger(__name__)


class Parser(Protocol):
    """What `documents.py` depends on. Nothing above this line knows or cares
    which library produced the text."""

    name: str

    def parse_html(self, html: str, url: str, selectors: SiteSelectors) -> Extracted: ...
    def parse_pdf(self, content: bytes) -> str: ...


# ── Your parsers go here ──────────────────────────────────────────────────
#
# Write a class per approach you want to be able to switch between. Each needs
# a `name`, `parse_html` and `parse_pdf`. Import third-party libraries lazily
# inside __init__ so that a parser nobody is using does not have to be
# installed — and raise a clear message when it is missing, naming the
# `uv add` that fixes it.
#
# Whatever you write, one rule holds: a single unreadable file must not fail an
# extract run over a whole site. Log it, return "", move on.


def build_parser(name: str = "") -> Parser:
    """Map the `parser:` string in an extract config to one of your parsers.

    Raise ValueError for an unknown name, and say what IS supported — a typo in
    a config should tell you the options, not fail with a KeyError three frames
    down.
    """
    raise NotImplementedError
