"""What else is on this page: links, linked files, images.

This is the only HTML parsing the crawl team does, and it is *structural* — it
answers "what should I fetch next", never "what does this page say". Reading a
page for meaning is Team B's job, and it happens later, offline, from the HTML
you saved beside this record.

Keeping the two apart is what stops an extraction tweak from costing a re-crawl.
Resist the urge to pull out the article text here; you will be undoing it later.

TEAM A OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

beautifulsoup4   with the "lxml" parser: BeautifulSoup(html, "lxml").
                 find_all("a", href=True), find_all("img"), .get("href").
urllib.parse     urljoin to make relative links absolute, urlparse to look at
                 the path when deciding if a link is a file.

"""

from __future__ import annotations

from dataclasses import dataclass, field

# Linked files worth pulling down. PDFs are parsed downstream by Team B; the
# rest are stored so that adding a parser later needs no second crawl.
DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".csv")


@dataclass
class Discovered:
    """Everything structural one page tells us. No prose, by design."""

    links: list[str] = field(default_factory=list)
    document_links: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    canonical_url: str = ""
    lang: str = "en"


def discover(html: str, url: str) -> Discovered:
    """Read a page for what to fetch next.

    Four things to pull out:

    1. `links` — every <a href>, EXCLUDING mailto:, tel: and javascript:.
       Leave these as they appeared in the HTML (relative is fine); the
       Frontier resolves them — return `["/about"]`, not the absolute form.

    2. `document_links` — hrefs whose path ends in DOCUMENT_EXTENSIONS. These
       are files to download, NOT pages to crawl: a PDF must never reach the
       HTML parser. Return these **absolute** and de-duplicated, in the order
       first seen (dict.fromkeys preserves order; a set does not).

    3. `images` — one dict per <img> with keys {ordinal, src, alt}. Make `src`
       absolute. Skip data: URIs and empty srcs. `ordinal` is the position on
       the page, so ordering survives into the record.

    4. `canonical_url` from <link rel="canonical">, and `lang` from
       <html lang="...">. Both may be absent; default lang to "en".

    A page that is one <a href="/docs/terms.pdf"> and one <a href="/about">
    must produce document_links=["https://.../docs/terms.pdf"] and
    links=["/about"] — never both in one list.
    """
    raise NotImplementedError
