"""HTTP with manners: robots.txt, a real User-Agent, rate limiting and retries.

These are not optional extras to bolt on later — an impolite crawler gets the
whole team's IP blocked on the first serious run, and you cannot un-block it
before the deadline. Build this file first; everything else in the crawl depends
on it behaving.

TEAM A OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

requests                 the HTTP client. Use a Session so connections and
                         headers are reused across the whole crawl.
urllib.robotparser       stdlib. RobotFileParser.can_fetch() does the whole
                         robots.txt job for you.
time.monotonic / sleep   for the per-host delay. monotonic, not time(), because
                         it cannot jump backwards.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from engine.contracts.documents import RawAsset, RawPage

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "CortexEngine/0.1 (+https://github.com/BdREN-Innovation/Cortex)"


@dataclass
class FetchPolicy:
    """Everything about how hard we are allowed to hit a server.

    Given to you — these fields are read from `configs/crawl.<site>.yaml`, so
    changing them changes the config contract. Add fields if you need them.
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
    """One instance per crawl. Tracks per-host timing and robots rules.

    State you will need: a requests.Session, a dict of host -> last request
    time, and a cache of origin -> parsed robots.txt (fetching robots.txt once
    per page would itself be abusive).
    """

    def __init__(self, policy: FetchPolicy | None = None):
        raise NotImplementedError(
            "Build a Session with the User-Agent header set, plus the two "
            "caches described in the class docstring."
        )

    # -- politeness ---------------------------------------------------------
    def allowed(self, url: str) -> bool:
        """Does robots.txt permit us to fetch this URL?

        Fetch and parse `<scheme>://<host>/robots.txt` once per origin and
        cache it. A missing robots.txt (404) means allow-all, per the standard —
        do not treat it as a failure. A robots.txt you cannot reach at all is
        also allow-all, but log a warning.

        Return True immediately when `policy.obey_robots` is False. That switch
        exists only for sites you own.
        """
        raise NotImplementedError

    def _wait_turn(self, host: str) -> None:
        """Block until `delay_seconds` has passed since the last hit on `host`.

        Per host, not global: crawling two domains should not halve your rate on
        either. Record the time *after* sleeping.
        """
        raise NotImplementedError

    # -- fetching -----------------------------------------------------------
    def fetch(self, url: str) -> RawPage | None:
        """GET an HTML page.

        Returns None (not an exception) for anything that is not our problem:
        robots.txt disallowed it, or the response is not HTML. Non-HTML is
        deliberate — a PDF must not reach the HTML parser. Binaries go through
        `fetch_asset` instead.

        Raise only when every retry failed, so `crawl()` can record it as an
        error against that URL and carry on with the rest of the site.

        Retry 429/502/503/504 with exponential backoff, and honour a
        `Retry-After` header when the server sends one. Do NOT retry a 404 —
        it will still be a 404.

        Truncate the body at `policy.max_bytes`.
        """
        raise NotImplementedError

    def fetch_asset(self, url: str) -> RawAsset | None:
        """Download a non-HTML file: a PDF, an image, a spreadsheet.

        Deliberately separate from `fetch`, which refuses non-HTML. Same robots
        rules, same rate limit, same session — an asset download is still a
        request to someone else's server.

        Stream the response (`stream=True`, then `iter_content`) and abort once
        `policy.max_asset_bytes` is exceeded. Reading a surprise 2 GB file into
        memory before checking its size will end the run on an 8 GB laptop.
        """
        raise NotImplementedError
