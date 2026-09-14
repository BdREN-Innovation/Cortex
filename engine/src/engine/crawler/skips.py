"""Why a URL did not end up in pages.jsonl or docs/.

A crawl that silently drops URLs cannot be audited: nobody can tell a page the
site does not have from one the crawler refused, failed, or never reached. So
every URL that is left out gets a `Skip` saying why, and the run writes them to
`skipped_pages.jsonl` and `failed_documents.jsonl` beside `pages.jsonl`.

TEAM A OWNS THIS FILE.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# robots.txt disallows it for our User-Agent.
ROBOTS = "robots"
# The server answered 4xx / 5xx (5xx and 429 only after the retries ran out).
HTTP_4XX = "http_4xx"
HTTP_5XX = "http_5xx"
# Bigger than fetch.max_bytes (pages) or fetch.max_asset_bytes (documents).
TOO_LARGE = "too_large"
# Outside allowed_domains, or ruled out by include/exclude patterns.
OFF_SCOPE = "off_scope"
# Only ever reached deeper than max_depth.
MAX_DEPTH = "max_depth"
# Not a URL the crawler can canonicalise.
INVALID_URL = "invalid_url"
# No usable response: network error, timeout, or the browser render failed.
FETCH_FAILED = "fetch_failed"
# Its canonical URL was already captured from another address.
DUPLICATE = "duplicate"
# Still queued when max_pages was reached.
MAX_PAGES = "max_pages"
# Linked after assets.max_documents files had been saved.
MAX_DOCUMENTS = "max_documents"
# Still queued when the crawl stopped on an unexpected error.
CRAWL_STOPPED = "crawl_stopped"
# Fetched, but reading links from it or saving it to disk failed.
DISCOVER_FAILED = "discover_failed"
WRITE_FAILED = "write_failed"


def http_reason(status: int) -> str:
    """Map an HTTP error status to its skip reason."""

    return HTTP_5XX if status >= 500 else HTTP_4XX


@dataclass
class Skip:
    """One URL left out of the capture, and why."""

    url: str
    reason: str
    status: int = 0
    detail: str = ""
    # The page that linked to it, when known. Seeds have none.
    parent_url: str = ""
    depth: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)
