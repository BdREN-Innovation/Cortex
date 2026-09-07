"""URL queue, scope rules and de-duplication."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

# Query parameters that never change the content, only the analytics.
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|mc_cid|mc_eid|ref|source$)")


def canonicalize(url: str) -> str:
    """Collapse the many spellings of one page into a single key.

    Without this the crawler happily indexes /page, /page/, /page?utm_source=x
    and /page#section as four separate documents.
    """
    url, _ = urldefrag(url)
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if (scheme == "http" and netloc.endswith(":80")) or (scheme == "https" and netloc.endswith(":443")):
        netloc = netloc.rsplit(":", 1)[0]

    path = re.sub(r"/{2,}", "/", parsed.path) or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = []
    for pair in parsed.query.split("&"):
        if not pair:
            continue
        key = pair.split("=", 1)[0]
        if not TRACKING_PARAMS.match(key):
            kept.append(pair)
    query = "&".join(sorted(kept))

    return urlunparse((scheme, netloc, path, "", query, ""))


@dataclass
class ScopeRules:
    allowed_domains: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    max_depth: int = 3

    def __post_init__(self):
        self._include = [re.compile(p) for p in self.include_patterns]
        self._exclude = [re.compile(p) for p in self.exclude_patterns]

    def in_scope(self, url: str, depth: int) -> bool:
        if depth > self.max_depth:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if self.allowed_domains:
            host = parsed.netloc.lower().split(":")[0]
            if not any(host == d or host.endswith("." + d) for d in self.allowed_domains):
                return False
        if any(rx.search(url) for rx in self._exclude):
            return False
        if self._include and not any(rx.search(url) for rx in self._include):
            return False
        return True


class Frontier:
    """Breadth-first queue that never hands out the same page twice."""

    def __init__(self, seeds: list[str], rules: ScopeRules):
        self.rules = rules
        self.seen: set[str] = set()
        self._queue: deque[tuple[str, int]] = deque()
        for seed in seeds:
            self.add(seed, depth=0)

    def add(self, url: str, depth: int) -> bool:
        canonical = canonicalize(url)
        if canonical in self.seen:
            return False
        if not self.rules.in_scope(canonical, depth):
            return False
        self.seen.add(canonical)
        self._queue.append((canonical, depth))
        return True

    def add_links(self, base_url: str, links: list[str], depth: int) -> int:
        added = 0
        for link in links:
            try:
                absolute = urljoin(base_url, link)
            except ValueError:
                continue
            if self.add(absolute, depth):
                added += 1
        return added

    def __bool__(self) -> bool:
        return bool(self._queue)

    def __len__(self) -> int:
        return len(self._queue)

    def pop(self) -> tuple[str, int]:
        return self._queue.popleft()
