"""HTTP with manners: robots.txt, a real User-Agent, rate limiting and retries.

These are not optional extras to bolt on later — an impolite crawler gets the
whole team's IP blocked on the first serious run.
"""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from engine.contracts.documents import RawPage

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "CortexEngine/0.1 (+https://github.com/BdREN-Innovation/Cortex)"


@dataclass
class FetchPolicy:
    user_agent: str = DEFAULT_USER_AGENT
    delay_seconds: float = 1.0        # minimum gap between requests to one host
    timeout_seconds: float = 20.0
    max_retries: int = 2
    max_bytes: int = 5_000_000
    obey_robots: bool = True


class Fetcher:
    """One instance per crawl. Tracks per-host timing and robots rules."""

    def __init__(self, policy: FetchPolicy | None = None):
        self.policy = policy or FetchPolicy()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.policy.user_agent})
        self._last_request_at: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    # -- politeness ---------------------------------------------------------
    def _wait_turn(self, host: str) -> None:
        last = self._last_request_at.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            remaining = self.policy.delay_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at[host] = time.monotonic()

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]

        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(f"{origin}/robots.txt")
        try:
            response = self.session.get(
                f"{origin}/robots.txt", timeout=self.policy.timeout_seconds
            )
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                # No robots.txt is an allow-all, per the standard.
                parser.parse([])
        except requests.RequestException:
            log.warning("Could not read robots.txt for %s; assuming allow-all", origin)
            parser.parse([])

        self._robots[origin] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if not self.policy.obey_robots:
            return True
        parser = self._robots_for(url)
        return True if parser is None else parser.can_fetch(self.policy.user_agent, url)

    # -- fetching -----------------------------------------------------------
    def fetch(self, url: str) -> RawPage | None:
        if not self.allowed(url):
            log.info("robots.txt disallows %s", url)
            return None

        host = urlparse(url).netloc
        last_error: Exception | None = None

        for attempt in range(self.policy.max_retries + 1):
            self._wait_turn(host)
            started = time.monotonic()
            try:
                response = self.session.get(
                    url, timeout=self.policy.timeout_seconds, allow_redirects=True
                )
            except requests.RequestException as exc:
                last_error = exc
                log.warning("fetch failed (%s/%s) %s: %s",
                            attempt + 1, self.policy.max_retries + 1, url, exc)
                time.sleep(min(2 ** attempt, 8))
                continue

            elapsed_ms = int((time.monotonic() - started) * 1000)

            # Retry only on transient server-side conditions.
            if response.status_code in (429, 502, 503, 504) and attempt < self.policy.max_retries:
                retry_after = response.headers.get("Retry-After")
                pause = float(retry_after) if (retry_after or "").isdigit() else min(2 ** attempt, 8)
                log.info("status %s on %s; backing off %.1fs", response.status_code, url, pause)
                time.sleep(pause)
                continue

            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type.lower() and content_type:
                log.debug("skipping non-HTML %s (%s)", url, content_type)
                return None

            html = response.text[: self.policy.max_bytes]
            return RawPage(
                url=response.url,
                status=response.status_code,
                html=html,
                headers=dict(response.headers),
                elapsed_ms=elapsed_ms,
            )

        if last_error:
            raise last_error
        return None
