"""HTTP with manners: robots.txt, a real User-Agent, rate limiting and retries.

These are not optional extras to bolt on later — an impolite crawler gets the
whole team's IP blocked on the first serious run, and you cannot un-block it
before the deadline. Build this file first; everything else in the crawl depends
on it behaving.

TEAM A OWNS THIS FILE.

Decisions you own
-----------------
* Which HTTP client? Whatever you pick, reuse one connection pool across the
  whole crawl rather than opening a new one per request.
* How do you read and honour robots.txt? Do not write a parser for it — the
  standard library already has one, and the edge cases (a missing file, an
  unreachable one, wildcards) are subtler than they look.
* Rate limiting is per host, not global: crawling two domains should not halve
  your rate on either. What does that mean for how you track time?
* Which HTTP statuses are worth retrying, and which are pointless? A 404 will
  still be a 404. A 429 is the server telling you to slow down, sometimes with
  a header saying by how much.
* What is the failure contract? Some outcomes are ordinary (robots said no) and
  some are errors the crawl should record and move past. Returning None and
  raising mean different things — decide which is which and be consistent, or
  `pipeline.py` cannot tell them apart.
* What stops a surprise 2 GB file from ending the run on an 8 GB laptop?

"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from engine.contracts.documents import RawAsset, RawPage

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "CortexEngine/0.1 (+https://github.com/BdREN-Innovation/Cortex)"


@dataclass
class FetchPolicy:
    """How hard we are allowed to hit a server.

    Read from `configs/crawl.<site>.yaml`. Add, rename or drop fields as your
    design needs them — just keep the config and the dataclass in step.
    """

    user_agent: str = DEFAULT_USER_AGENT
    delay_seconds: float = 1.0  # minimum gap between requests to one host
    timeout_seconds: float = 20.0
    max_retries: int = 2
    max_bytes: int = 5_000_000
    # Binaries get their own ceiling: a 30-page PDF dwarfs any HTML page, and
    # capping both at 5 MB would silently truncate the useful ones.
    max_asset_bytes: int = 20_000_000
    obey_robots: bool = True


class Fetcher:
    """One instance per crawl. Tracks per-host timing and robots rules."""

    def __init__(self, policy: FetchPolicy | None = None):
        raise NotImplementedError

    # -- politeness ---------------------------------------------------------
    def allowed(self, url: str) -> bool:
        """Does robots.txt permit us to fetch this URL?

        Read it once per origin, not once per page — fetching robots.txt before
        every request is itself abusive.

        A missing robots.txt means allow-all, per the standard; so does one you
        cannot reach, though that is worth logging. `policy.obey_robots` is the
        override, and it exists only for sites you own.
        """
        raise NotImplementedError

    def _wait_turn(self, host: str) -> None:
        """Block until enough time has passed since the last request to `host`.

        Per host, not global. Beware of clocks that can jump backwards.
        """
        raise NotImplementedError

    # -- fetching -----------------------------------------------------------
    def fetch(self, url: str) -> RawPage | None:
        """GET an HTML page.

        Returning None and raising must mean different things, because `crawl()`
        treats them differently: one is an ordinary outcome to skip past, the
        other is an error to record against that URL. Decide which is which.

        This returns HTML only. A PDF must never reach the HTML parser — that
        is what `fetch_asset` is for.
        """
        raise NotImplementedError

    def fetch_asset(self, url: str) -> RawAsset | None:
        """Download a non-HTML file: a PDF, a spreadsheet.

        Separate from `fetch`, which refuses non-HTML — but the same robots
        rules and the same rate limit apply. An asset download is still a
        request to somebody else's server.

        These can be large. Reading a surprise 2 GB file fully into memory
        before checking its size will end the run on an 8 GB laptop, so find a
        way to stop before that happens.
        """
        raise NotImplementedError
