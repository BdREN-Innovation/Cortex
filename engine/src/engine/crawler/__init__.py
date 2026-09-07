"""Team A: fetch a site politely and capture what is there.

Emits CrawledPage records plus the bytes they point at. Interpreting those bytes
is `engine extract`, which the knowledge team owns.
"""

from engine.crawler.discover import Discovered, discover
from engine.crawler.pipeline import AssetPolicy, CrawlConfig, crawl

__all__ = ["CrawlConfig", "AssetPolicy", "crawl", "discover", "Discovered"]
