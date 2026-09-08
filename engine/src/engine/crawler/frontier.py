"""The queue: what to visit next, and what is out of bounds.

Two jobs live here, and the first is quietly the most important thing in the
crawler. `canonicalize` is what stops you storing `/pricing`, `/pricing/`,
`/pricing?utm_source=twitter` and `/pricing#plans` as four separate documents
that then come back as four separate search results.

TEAM A OWNS THIS FILE.

Decisions you own
-----------------
* What exactly makes two URLs "the same page"? The examples below pin the cases
  that matter here; you decide how to get there.
* What do you do with the root path — does `https://x.test/` keep its slash?
  Either answer is defensible; an inconsistent one breaks joins downstream.
* Which query parameters are noise? `utm_*` obviously. What about `ref`,
  `source`, session ids, a `page=` you actually need? This list grows as you
  meet real sites.
* Breadth-first or depth-first? BFS finds the shallow, important pages first,
  which matters when `max_pages` cuts you off mid-crawl.
* What data structure makes "have I seen this?" cheap at 10,000 URLs?

"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Query parameters that never change the content, only the analytics.
# Strip them before comparing URLs. Extend as you meet real sites.
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|mc_cid|mc_eid|ref$|source$)")


def canonicalize(url: str) -> str:
    """Collapse the many URLs that mean one page into a single string.

    Required behaviour — these examples are the specification:

        https://X.test/a/                -> https://x.test/a
        https://x.test/a#section         -> https://x.test/a
        https://x.test/a?utm_source=news -> https://x.test/a
        https://x.test/a?b=2&a=1         -> https://x.test/a?a=1&b=2
        https://x.test//a//b             -> https://x.test/a/b
        https://x.test:443/a             -> https://x.test/a

    This function's output becomes `page_id`, so it must be stable across runs
    and across machines.
    """
    raise NotImplementedError


@dataclass
class ScopeRules:
    """What counts as in-bounds for this crawl. All four come from the config."""

    allowed_domains: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    max_depth: int = 3

    def __post_init__(self):
        """You will test these patterns against thousands of URLs. Prepare them
        here rather than on every call."""
        raise NotImplementedError

    def in_scope(self, url: str, depth: int) -> bool:
        """Should we fetch this URL at this depth?

        Four things can put a URL out of bounds: it is too deep, it is on a
        host we are not crawling, it matches something excluded, or it fails to
        match anything included. Watch the difference between "no include
        patterns configured" and "include patterns configured and none matched"
        — they must not mean the same thing.

        An empty `allowed_domains` means no domain restriction here; the caller
        derives a default from the seeds before constructing you.
        """
        raise NotImplementedError


class Frontier:
    """Breadth-first queue that never hands out the same page twice.

    The de-duplication key is the *canonical* URL, not the raw one. That is the
    whole reason canonicalize exists: two different-looking links to the same
    page must collide here rather than becoming two documents.
    """

    def __init__(self, seeds: list[str], rules: ScopeRules):
        raise NotImplementedError

    def add(self, url: str, depth: int) -> bool:
        """Queue one URL. Returns True if it was actually added.

        False when the URL is out of scope or has been seen before.
        """
        raise NotImplementedError

    def add_links(self, base_url: str, links: list[str], depth: int) -> int:
        """Queue every link found on a page. Returns how many were added.

        `links` are as they appeared in the HTML, so they may be relative
        ("/docs/billing", "../index.html") and need resolving against
        `base_url` first.
        """
        raise NotImplementedError

    def __bool__(self) -> bool:
        """True while there is anything left to crawl — `while frontier:`."""
        raise NotImplementedError

    def pop(self) -> tuple[str, int]:
        """Take the next (url, depth). Breadth-first: oldest first."""
        raise NotImplementedError
