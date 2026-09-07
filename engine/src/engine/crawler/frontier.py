"""The queue: what to visit next, and what is out of bounds.

Two jobs live here, and the first is quietly the most important thing in the
crawler. `canonicalize` is what stops you storing `/pricing`, `/pricing/`,
`/pricing?utm_source=twitter` and `/pricing#plans` as four separate documents
that then come back as four separate search results.

TEAM A OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

urllib.parse   urlparse, urlunparse, parse_qsl, urlencode, urljoin, urldefrag.
               Everything canonicalize needs is here; a third-party URL
               library is unlikely to earn its place here.
re             compiled patterns for include/exclude rules.
collections    deque, for a breadth-first queue with cheap popleft().

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

    So: lowercase scheme and host, drop the default port (80 for http, 443 for
    https), collapse repeated slashes, drop a trailing slash, drop the fragment
    entirely, remove tracking params, and sort the remaining query parameters so
    that argument order stops mattering.

    This function's output becomes `page_id`, so it must be stable across runs.
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
        """Compile the regexes once here, not on every URL you test."""
        raise NotImplementedError

    def in_scope(self, url: str, depth: int) -> bool:
        """Should we fetch this URL at this depth?

        Check cheapest-and-most-decisive first:
          - depth is within max_depth
          - the scheme is http or https (not mailto:, javascript:, data:)
          - the host is in allowed_domains, or is a subdomain of one
          - no exclude_pattern matches
          - if include_patterns is non-empty, at least one matches

        An empty `allowed_domains` means no domain restriction here — the
        caller derives the default from the seeds before constructing you.
        """
        raise NotImplementedError


class Frontier:
    """Breadth-first queue that never hands out the same page twice.

    The de-duplication key is the *canonical* URL, not the raw one. That is the
    whole reason canonicalize exists: two different-looking links to the same
    page must collide here rather than becoming two documents.
    """

    def __init__(self, seeds: list[str], rules: ScopeRules):
        raise NotImplementedError(
            "Hold the rules, a set of seen canonical URLs, and a deque of "
            "(url, depth). Push each seed at depth 0 through self.add()."
        )

    def add(self, url: str, depth: int) -> bool:
        """Queue one URL. Returns True if it was actually added.

        False when the URL is out of scope or has been seen before. Returning a
        bool rather than nothing is what makes the behaviour testable.
        """
        raise NotImplementedError

    def add_links(self, base_url: str, links: list[str], depth: int) -> int:
        """Queue every link found on a page. Returns how many were added.

        `links` are as they appeared in the HTML, so they may be relative
        ("/docs/billing", "../index.html"). Resolve each against `base_url`
        first — urllib.parse.urljoin does exactly this.
        """
        raise NotImplementedError

    def __bool__(self) -> bool:
        """True while there is anything left to crawl — `while frontier:`."""
        raise NotImplementedError

    def pop(self) -> tuple[str, int]:
        """Take the next (url, depth). Breadth-first: oldest first."""
        raise NotImplementedError
