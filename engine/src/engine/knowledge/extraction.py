"""Saved HTML -> title, clean prose, tables, breadcrumb.

Run *offline* against the HTML Team A captured. That is the point: reading a
page differently costs a re-extract (about a second) instead of a re-crawl (an
hour, and another thousand requests to somebody else's server).

This file decides how good everything downstream can possibly be. If chrome
leaks into `text`, it gets embedded, retrieved, and returned to a user as an
answer. Judge your work by reading the output, not by whether it runs.

TEAM B OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

beautifulsoup4   with "lxml". soup.select_one(css), node.decompose(),
                 node.replace_with(NavigableString(...)), get_text(separator).
re               whitespace collapsing.
Worth evaluating as alternatives to the hand-rolled main-content hunt:
  trafilatura        boilerplate removal, purpose-built for exactly this
  readability-lxml   the Readability algorithm
  justext            another boilerplate remover
Try one against a real site before deciding — they can beat hand-tuned
selectors on messy sites and lose badly on clean documentation sites.

"""

from __future__ import annotations

from dataclasses import dataclass, field

# Elements that are never page content.
STRIP_TAGS = ["script", "style", "noscript", "template", "svg", "iframe", "form"]
# Elements that are usually chrome. Remove only when the page has a <main> or
# <article> to fall back on, so a simple page is never blanked out entirely.
CHROME_TAGS = ["nav", "header", "footer", "aside"]

MAIN_SELECTORS = ["main", "article", "[role=main]", "#content", ".content", "#main"]


@dataclass
class SiteSelectors:
    """Per-site overrides, set in `configs/extract.<site>.yaml` — never in code.

    One config file per site means nobody edits a shared module to fix a site,
    so several people can tune several sites at once without colliding.

    Reach for these only when the generic extractor gets a page wrong.
    """

    # CSS selector for the element holding the article body. Overrides the
    # generic <main>/<article> hunt.
    main: str = ""
    # Selectors to delete before extracting: cookie bars, "related articles",
    # share widgets — anything repeated on every page that would poison chunks.
    drop: list[str] = field(default_factory=list)
    # CSS selector for the breadcrumb, when the generic hunt misses it.
    breadcrumb: str = ""


@dataclass
class Extracted:
    """One page, read for meaning."""

    title: str
    text: str
    section_path: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    # Markdown renderings of every <table>, in page order. Already inlined into
    # `text`; carried separately so the caller can mirror them to tables/.
    tables: list[dict] = field(default_factory=list)


def rows_to_markdown(rows: list[list[str]]) -> str:
    """Render a grid of cells as a markdown table.

    Shared by the HTML path and the PDF path — a table is a table whichever
    format it arrived in, so build this once and call it from both.

    Two rules that must hold:
      * Pad every row to the width of the widest one. A ragged markdown table
        stops being a table.
      * Escape "|" inside a cell, or one stray pipe splits the row into two
        columns and shifts everything after it. Escape exactly once.

    Row 0 becomes the header, followed by the "| --- | --- |" separator.
    Return "" for an empty grid rather than a header with no rows.
    """
    raise NotImplementedError


def table_to_markdown(table) -> str:
    """Render one BeautifulSoup <table> as markdown, via rows_to_markdown.

    Walk <tr>, then <th>/<td>. Handle colspan by repeating the value across the
    span, so a merged cell stays attached to every column it covered.
    """
    raise NotImplementedError


def extract(html: str, url: str, selectors: SiteSelectors | None = None) -> Extracted:
    """Read saved HTML for meaning.

    Order matters here, and getting it wrong is the usual bug:

      1. Apply `selectors.drop` FIRST. Junk removed now cannot contaminate the
         title, the breadcrumb or anything after it.
      2. Pull <meta> description/author/keywords into `meta`.
      3. Title: <title>, falling back to the first <h1>.
      4. Breadcrumb into `section_path`: `selectors.breadcrumb` if given, else
         hunt for class/aria-label containing "breadcrumb", else fall back to
         the page's own h1/h2 heading hierarchy. **Citations depend on this** —
         an empty section_path produces an answer that cannot say where it came
         from.
      5. Strip STRIP_TAGS.
      6. Find the body: `selectors.main` if given, else the first hit among
         MAIN_SELECTORS, else drop CHROME_TAGS and use <body>.
      7. Tables -> markdown, replacing each <table> node **in place** so the
         markdown lands where the table was. A table ripped out of its page is
         a grid of numbers with nothing saying what they mean; the chunker can
         only embed what is adjacent.
      8. Replace each <img> with its alt text — but ONLY when the alt is
         descriptive. "Revenue by quarter" must survive; "logo" must be
         dropped. Judge by word count, not length: a description is a phrase,
         chrome is a label. `<figcaption>` is already text in the DOM and
         comes through on its own.

         Nobody downloads the image itself — see crawler/discover.py. The alt
         text is prose, so it belongs in the document; the pixels have no path
         to an answer.
      9. Collapse whitespace and return.

    Note what is NOT here: links, canonical URL and lang. Those are Team A's
    business and arrive on the CrawledPage record. This module reads for
    meaning only.
    """
    raise NotImplementedError
