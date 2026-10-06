"""The queue: what to visit next, and what is out of bounds.

TEAM A OWNS THIS FILE.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from engine.crawler import skips
from engine.crawler.skips import Skip


# Query parameters that normally do not change page content.
#
# We intentionally remove only well-known tracking parameters.
# Functional parameters such as ?page=2, ?category=laptop, ?id=123, etc.
# are preserved because they may point to genuinely different content.
TRACKING_PARAMS = re.compile(
    r"^(?:"
    r"utm_.*|"
    r"fbclid|"
    r"gclid|"
    r"dclid|"
    r"msclkid|"
    r"mc_cid|"
    r"mc_eid|"
    r"ref|"
    r"source|"
    r"_ga|"
    r"_gl"
    r")$",
    re.IGNORECASE,
)


def canonicalize(url: str) -> str:
    """Return one stable URL for URLs that represent the same page.

    Examples:
        https://X.test/a/                  -> https://x.test/a
        https://x.test/a#section           -> https://x.test/a
        https://x.test/a?utm_source=news   -> https://x.test/a
        https://x.test/a?b=2&a=1           -> https://x.test/a?a=1&b=2
        https://x.test//a//b                -> https://x.test/a/b
        https://x.test:443/a                -> https://x.test/a
    """
    parts = urlsplit(url.strip())

    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid absolute URL: {url}")

    scheme = parts.scheme.lower()

    # Only HTTP(S) URLs belong in the web frontier.
    if scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {scheme}")

    hostname = parts.hostname
    if not hostname:
        raise ValueError(f"Invalid URL hostname: {url}")

    hostname = hostname.lower()

    # Preserve a non-default port.
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"Invalid URL port: {url}") from exc

    if port is not None:
        if not (
            (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            hostname = f"{hostname}:{port}"

    # Collapse repeated slashes.
    path = re.sub(r"/+", "/", parts.path or "/")

    # Root keeps its slash, other paths lose an unnecessary trailing slash.
    if path != "/":
        path = path.rstrip("/")

    # Remove known tracking parameters while preserving functional query params.
    query_params = [
        (key, value)
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if not TRACKING_PARAMS.match(key)
    ]

    # Query order should not make an otherwise identical URL unique.
    query_params.sort()

    query = urlencode(query_params, doseq=True)

    # URL fragments are client-side anchors and are not separate pages.
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

    def __post_init__(self) -> None:
        """Compile include/exclude regex patterns once."""
        self._include_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.include_patterns
        ]

        self._exclude_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.exclude_patterns
        ]

        self.allowed_domains = [
            domain.lower().strip().rstrip(".")
            for domain in self.allowed_domains
            if domain.strip()
        ]

    def in_scope(self, url: str, depth: int) -> bool:
        """Return True if a URL should be crawled."""
        return self.out_of_scope_reason(url, depth) is None

    def out_of_scope_reason(self, url: str, depth: int) -> str | None:
        """Return why a URL should not be crawled, or None if it should."""
        if depth > self.max_depth:
            return skips.MAX_DEPTH

        try:
            canonical_url = canonicalize(url)
            hostname = (urlsplit(canonical_url).hostname or "").lower()
        except ValueError:
            return skips.INVALID_URL

        if self.allowed_domains:
            domain_allowed = any(
                hostname == domain
                or hostname.endswith("." + domain)
                for domain in self.allowed_domains
            )

            if not domain_allowed:
                return skips.OFF_SCOPE

        # Exclusions always win.
        if any(
            pattern.search(canonical_url)
            for pattern in self._exclude_patterns
        ):
            return skips.OFF_SCOPE

        # If include patterns exist, at least one must match.
        if self._include_patterns:
            if not any(
                pattern.search(canonical_url)
                for pattern in self._include_patterns
            ):
                return skips.OFF_SCOPE

        return None


class Frontier:
    """Breadth-first queue that never hands out the same canonical URL twice."""

    def __init__(self, seeds: list[str], rules: ScopeRules):
        self.rules = rules
        self._queue: deque[tuple[str, int]] = deque()
        self._seen: set[str] = set()
        # The page each queued URL was first found on. Seeds have none.
        self._parents: dict[str, str] = {}
        # URLs turned away, one record per URL, keyed by canonical form.
        self._skipped: dict[str, Skip] = {}

        for seed in seeds:
            self.add(seed, 0)

    def add(self, url: str, depth: int, parent_url: str = "") -> bool:
        """Queue one URL if it is valid, in scope, and unseen.

        A URL turned away is remembered with the reason, unless it is queued
        later: a link too deep on one page may be shallow on another.
        """
        try:
            canonical_url = canonicalize(url)
        except ValueError:
            self._skipped.setdefault(
                url,
                Skip(url=url, reason=skips.INVALID_URL, parent_url=parent_url, depth=depth),
            )
            return False

        if canonical_url in self._seen:
            return False

        reason = self.rules.out_of_scope_reason(canonical_url, depth)

        if reason is not None:
            self._skipped.setdefault(
                canonical_url,
                Skip(url=canonical_url, reason=reason, parent_url=parent_url, depth=depth),
            )
            return False

        self._skipped.pop(canonical_url, None)
        self._seen.add(canonical_url)
        self._parents[canonical_url] = parent_url
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

            if self.add(absolute_url, next_depth, parent_url=base_url):
                added += 1

        return added

    def parent_of(self, url: str) -> str:
        """The page a queued URL was first found on, or "" for a seed."""
        return self._parents.get(url, "")

    def skipped(self) -> list[Skip]:
        """Every URL turned away so far, with the reason."""
        return list(self._skipped.values())

    def drain(self, reason: str) -> list[Skip]:
        """Empty the queue, recording each URL left in it as skipped for `reason`."""
        left: list[Skip] = []

        while self._queue:
            url, depth = self._queue.popleft()
            left.append(
                Skip(url=url, reason=reason, parent_url=self.parent_of(url), depth=depth)
            )

        return left

    def __bool__(self) -> bool:
        """True while URLs remain in the queue."""
        return bool(self._queue)

    def pop(self) -> tuple[str, int]:
        """Take the oldest URL from the queue."""
        return self._queue.popleft()