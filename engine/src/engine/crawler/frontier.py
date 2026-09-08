"""The queue: what to visit next, and what is out of bounds.

TEAM A OWNS THIS FILE.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Query parameters that normally do not change page content.
TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid|gclid|mc_cid|mc_eid|ref$|source$)",
    re.IGNORECASE,
)


def canonicalize(url: str) -> str:
    """Return one stable URL for URLs that represent the same page.

    Examples:
        https://X.test/a/                 -> https://x.test/a
        https://x.test/a#section          -> https://x.test/a
        https://x.test/a?utm_source=news  -> https://x.test/a
        https://x.test/a?b=2&a=1          -> https://x.test/a?a=1&b=2
        https://x.test//a//b              -> https://x.test/a/b
        https://x.test:443/a              -> https://x.test/a
    """
    parts = urlsplit(url.strip())

    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid absolute URL: {url}")

    scheme = parts.scheme.lower()

    # urlsplit().hostname removes the brackets from IPv6 addresses and
    # lowercases normal hostnames.
    hostname = parts.hostname
    if not hostname:
        raise ValueError(f"Invalid URL hostname: {url}")

    hostname = hostname.lower()

    # Preserve a non-default port.
    port = parts.port
    if port is not None:
        if not (
            (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            hostname = f"{hostname}:{port}"

    # Collapse repeated slashes in the path.
    path = re.sub(r"/+", "/", parts.path or "/")

    # Keep the root slash, but remove unnecessary trailing slashes elsewhere.
    if path != "/":
        path = path.rstrip("/")

    # Remove tracking parameters and sort the remaining parameters.
    query_params = [
        (key, value)
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if not TRACKING_PARAMS.match(key)
    ]

    query_params.sort()

    query = urlencode(query_params, doseq=True)

    # Fragment is deliberately removed.
    return urlunsplit(
        (
            scheme,
            hostname,
            path,
            query,
            "",
        )
    )


@dataclass
class ScopeRules:
    """What counts as in-bounds for this crawl."""

    allowed_domains: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    max_depth: int = 3

    def __post_init__(self):
        """Compile include/exclude regex patterns once."""
        self._include_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.include_patterns
        ]

        self._exclude_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.exclude_patterns
        ]

        # Normalize allowed domains.
        self.allowed_domains = [
            domain.lower().strip().rstrip(".")
            for domain in self.allowed_domains
            if domain.strip()
        ]

    def in_scope(self, url: str, depth: int) -> bool:
        """Return True if a URL should be crawled."""
        if depth > self.max_depth:
            return False

        try:
            canonical_url = canonicalize(url)
            hostname = (urlsplit(canonical_url).hostname or "").lower()
        except ValueError:
            return False

        # Domain restriction.
        if self.allowed_domains:
            domain_allowed = any(
                hostname == domain
                or hostname.endswith("." + domain)
                for domain in self.allowed_domains
            )

            if not domain_allowed:
                return False

        # Exclusions always win.
        if any(
            pattern.search(canonical_url)
            for pattern in self._exclude_patterns
        ):
            return False

        # If include patterns exist, at least one must match.
        if self._include_patterns:
            if not any(
                pattern.search(canonical_url)
                for pattern in self._include_patterns
            ):
                return False

        return True


class Frontier:
    """Breadth-first queue that never hands out the same page twice."""

    def __init__(self, seeds: list[str], rules: ScopeRules):
        self.rules = rules
        self._queue: deque[tuple[str, int]] = deque()
        self._seen: set[str] = set()

        # Add seeds at depth 0.
        for seed in seeds:
            self.add(seed, 0)

    def add(self, url: str, depth: int) -> bool:
        """Queue one URL if it is valid, in scope, and unseen."""
        try:
            canonical_url = canonicalize(url)
        except ValueError:
            return False

        if canonical_url in self._seen:
            return False

        if not self.rules.in_scope(canonical_url, depth):
            return False

        self._seen.add(canonical_url)
        self._queue.append((canonical_url, depth))

        return True

    def add_links(
        self,
        base_url: str,
        links: list[str],
        depth: int,
    ) -> int:
        """Resolve and queue links discovered on a page.

        Links discovered from a page at depth N are queued at depth N + 1.
        """
        added = 0
        next_depth = depth + 1

        for link in links:
            link = link.strip()

            if not link:
                continue

            absolute_url = urljoin(base_url, link)

            if self.add(absolute_url, next_depth):
                added += 1

        return added

    def __bool__(self) -> bool:
        """True while URLs remain in the queue."""
        return bool(self._queue)

    def pop(self) -> tuple[str, int]:
        """Take the oldest URL from the queue."""
        return self._queue.popleft()