"""Capture a site: fetch pages and linked files, save the bytes, record what was found.

This stage deliberately produces **no text**. It writes `pages.jsonl` — one
`CrawledPage` per URL — beside the bytes those records point at. Turning bytes
into documents is `engine extract`, which Team B owns.

The split is not tidiness. It means an extraction change costs a re-extract
(seconds, offline) instead of a re-crawl (an hour, and another thousand requests
to somebody else's server), so the two teams stop blocking each other on day four.

TEAM A OWNS THIS FILE. It is the last one to build — it only chains together
fetcher.py, frontier.py and discover.py.

Decisions you own
-----------------
* How is a run identified? It has to sort sensibly and never collide with a
  previous run of the same site.
* A URL has to become a safe filename. What happens to a URL containing `..`,
  or a 400-character path, or characters your filesystem rejects?
* What goes in the manifest? It is the only record of how a run went once the
  terminal output is gone — think about what you would want to see when a
  crawl produced half as many pages as you expected.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from engine.crawler.fetcher import FetchPolicy

log = logging.getLogger(__name__)


@dataclass
class AssetPolicy:
    """What to download besides HTML.

    Nothing here is interpreted — these are fetch decisions. Whether a PDF gets
    parsed into a document is decided downstream by Team B.

    Images are not downloaded at all: nothing in the pipeline can use a PNG,
    so fetching them costs bandwidth and disk for no gain.
    """

    download_documents: bool = True
    # Linked files get their own budget. One 300-page manual must not compete
    # with pages for `max_pages`.
    max_documents: int = 25


@dataclass
class CrawlConfig:
    """Read from `configs/crawl.<site>.yaml`. One file per site, one owner each."""

    site: str
    seeds: list[str]
    allowed_domains: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    max_depth: int = 3
    max_pages: int = 200
    fetch: FetchPolicy = field(default_factory=FetchPolicy)
    assets: AssetPolicy = field(default_factory=AssetPolicy)

    @classmethod
    def from_dict(cls, payload: dict) -> "CrawlConfig":
        """Build from parsed YAML.

        The nested `fetch:` and `assets:` blocks become FetchPolicy and
        AssetPolicy. Ignore unknown top-level keys rather than crashing — a
        config with a typo should not take down a crawl at minute forty.
        """
        raise NotImplementedError


def crawl(config: CrawlConfig, out_root: str | Path = "data", run_id: str | None = None) -> Path:
    """Capture a site. Writes pages.jsonl + manifest.json. Returns the run directory.

    Layout to produce — one folder per site per run:

        <out_root>/sites/<site>/<run_id>/
        ├── pages.jsonl      one CrawledPage per line
        ├── manifest.json    a CrawlManifest
        ├── raw/<page_id>.html
        └── docs/<filename>          (linked PDFs etc.)

    `content_path` on each record is **relative to the run directory**, so the
    whole folder stays movable. Team B joins it back.

    Must produce, for one site:

      * every in-scope page fetched, its bytes on disk, one record each
      * linked documents downloaded, within their own budget, recorded the
        same way
      * a manifest describing how the run went

    Three things that are easy to get wrong:

      * One bad page must never kill a run. A crawl that dies at page 180 of
        200 has produced nothing.
      * A linked file is a leaf, not another hop. Think about what that means
        for depth — and note that scope rules should still apply to it.
      * There is NO thin-page filter and NO duplicate-text detection here.
        Both need the text, and there is no text at this stage. `/` and
        `/index.html` will both be captured; Team B collapses them. Do not try
        to be clever and dedupe on raw HTML — identical pages routinely differ
        by a timestamp or a CSRF token.

      One more, about ordering: linked documents can be large and slow. Think
      about when you fetch them relative to the page crawl.

    """
    raise NotImplementedError
