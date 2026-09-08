"""Saved HTML -> title, clean prose, tables, breadcrumb.

Run *offline* against the HTML Team A captured. That is the point: reading a
page differently costs a re-extract (about a second) instead of a re-crawl (an
hour, and another thousand requests to somebody else's server).

This file decides how good everything downstream can possibly be. If chrome
leaks into `text`, it gets embedded, retrieved, and returned to a user as an
answer. Judge your work by reading the output, not by whether it runs.

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
* What parses the HTML, and do you hand-roll the main-content hunt or use
  something purpose-built for boilerplate removal? Both are reasonable; they
  win on different kinds of site. Try one against a real page before deciding.
* How do you find the main content when a page has no <main> or <article>?
* How do you know a breadcrumb when you see one? Sites disagree about markup.
  What is your fallback when there is none — and remember that an empty
  `section_path` produces an answer that cannot say where it came from.
* Alt text: some is content ("Revenue by quarter"), some is chrome ("logo").
  What is your rule for telling them apart? String length is a trap.
* What counts as whitespace worth collapsing, and what is meaningful layout?

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

    Worth building once and calling from both the HTML and the PDF path — a
    table is a table whichever format it arrived in.

    Two things will bite you: rows of unequal length stop being a table, and a
    cell containing a "|" splits itself into two columns unless you deal with
    it. Decide how, and make sure it happens exactly once.
    """
    raise NotImplementedError


def table_to_markdown(table) -> str:
    """Render one HTML table element as markdown.

    Real tables use `colspan` and `rowspan`. Work out what a merged cell should
    become in a flat markdown grid before you meet one in production.
    """
    raise NotImplementedError


def extract(html: str, url: str, selectors: SiteSelectors | None = None) -> Extracted:
    """Read saved HTML for meaning.

    Must produce: a title, clean prose with no site chrome in it, a breadcrumb
    in `section_path`, any `<meta>` worth keeping, and every `<table>` rendered
    as markdown.

    Tables belong **inline, where they were**. A table lifted out of its page is
    a grid of numbers with nothing saying what they mean; the chunker can only
    embed what is adjacent to it.

    One ordering constraint that is easy to get wrong: `selectors.drop` has to
    run before anything else reads the document. Junk removed late has already
    contaminated your title and your breadcrumb.

    Note what is NOT here: links, canonical URL and lang. Those are Team A's
    business and arrive on the CrawledPage record. This module reads for
    meaning only.
    """
    raise NotImplementedError
