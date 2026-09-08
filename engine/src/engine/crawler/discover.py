"""What else is on this page: links and linked files.

This is the only HTML parsing the crawl team does, and it is *structural* — it
answers "what should I fetch next", never "what does this page say". Reading a
page for meaning is Team B's job, and it happens later, offline, from the HTML
you saved beside this record.

Keeping the two apart is what stops an extraction tweak from costing a re-crawl.
Resist the urge to pull out the article text here; you will be undoing it later.

TEAM A OWNS THIS FILE.

Decisions you own
-----------------
* What parses the HTML? You need something that survives real-world markup —
  unclosed tags, wrong nesting, mixed encodings. A regex will not do it.
* Which file extensions count as "a document to download" rather than "a page
  to crawl"? Start with the obvious ones and extend as you meet real sites.
* Relative links, protocol-relative links (`//cdn.example.com/x`), `<base href>`
  — which of these do you resolve here, and which does the Frontier handle?
  Pick one place; doing it in both is how double-resolution bugs happen.

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
    canonical_url: str = ""
    lang: str = "en"


def discover(html: str, url: str) -> Discovered:
    """Read a page for what to fetch next.

    Three things to pull out:

    1. `links` — every <a href>, EXCLUDING mailto:, tel: and javascript:.
       Leave these as they appeared in the HTML (relative is fine); the
       Frontier resolves them — return `["/about"]`, not the absolute form.

    2. `document_links` — hrefs pointing at files rather than pages. A PDF must
       never reach the HTML parser. Return these absolute and de-duplicated,
       and think about whether order matters to you.

    3. `canonical_url` from <link rel="canonical">, and `lang` from
       <html lang="...">. Both may be absent; default lang to "en".

    Images are deliberately not here. Nothing downstream can use a PNG — the
    embedders are text-only — so downloading them costs bandwidth and disk for
    no gain. The alt text is the valuable part, and Team B reads that straight
    out of the saved HTML.

    A page that is one <a href="/docs/terms.pdf"> and one <a href="/about">
    must produce document_links=["https://.../docs/terms.pdf"] and
    links=["/about"] — never both in one list.
    """
    raise NotImplementedError
