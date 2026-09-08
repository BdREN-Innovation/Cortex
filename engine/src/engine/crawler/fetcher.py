"""HTTP with manners: robots.txt, a real User-Agent, rate limiting and retries.

TEAM A OWNS THIS FILE.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from engine.contracts.documents import RawAsset, RawPage

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "CortexEngine/0.1 "
    "(+https://github.com/BdREN-Innovation/Cortex)"
)

RETRYABLE_STATUSES = {429, 502, 503, 504}


@dataclass
class FetchPolicy:
    """How hard we are allowed to hit a server."""

    user_agent: str = DEFAULT_USER_AGENT
    delay_seconds: float = 1.0
    timeout_seconds: float = 20.0
    max_retries: int = 2
    max_bytes: int = 5_000_000
    max_asset_bytes: int = 20_000_000
    obey_robots: bool = True


class Fetcher:
    """One instance per crawl. Tracks per-host timing and robots rules."""

    def __init__(self, policy: FetchPolicy | None = None):
        self.policy = policy or FetchPolicy()

        self.client = httpx.Client(
            headers={"User-Agent": self.policy.user_agent},
            timeout=self.policy.timeout_seconds,
            follow_redirects=True,
        )

        # Last request time for each host.
        # Example:
        # {
        #     "cuet.ac.bd": 12345.67,
        #     "bdren.net.bd": 12350.21,
        # }
        self._last_request: dict[str, float] = {}

        # robots.txt rules cached by origin.
        self._robots: dict[str, RobotFileParser | None] = {}

    # ------------------------------------------------------------------
    # politeness
    # ------------------------------------------------------------------

    def allowed(self, url: str) -> bool:
        """Return True when robots.txt permits fetching this URL."""

        if not self.policy.obey_robots:
            return True

        parts = urlsplit(url)

        if not parts.scheme or not parts.netloc:
            log.warning("Invalid URL for robots check: %s", url)
            return False

        origin = f"{parts.scheme.lower()}://{parts.netloc.lower()}"

        # Reuse already downloaded robots.txt rules.
        if origin in self._robots:
            parser = self._robots[origin]

            if parser is None:
                return True

            return parser.can_fetch(self.policy.user_agent, url)

        robots_url = f"{origin}/robots.txt"

        try:
            self._wait_turn(parts.netloc.lower())

            started = time.monotonic()

            response = self.client.get(robots_url)

            elapsed = time.monotonic() - started

            log.debug(
                "robots.txt %s → %s in %.0f ms",
                robots_url,
                response.status_code,
                elapsed * 1000,
            )

            # A missing robots.txt means allow-all.
            if response.status_code == 404:
                self._robots[origin] = None
                return True

            # Other HTTP errors are treated conservatively.
            if response.status_code >= 400:
                log.warning(
                    "Could not read robots.txt for %s (HTTP %s); "
                    "allowing crawl but recording the problem.",
                    origin,
                    response.status_code,
                )
                self._robots[origin] = None
                return True

            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())

            self._robots[origin] = parser

            return parser.can_fetch(self.policy.user_agent, url)

        except (httpx.HTTPError, OSError) as exc:
            # If robots.txt cannot be reached, allow the request but log it.
            # This follows the scaffold's stated failure contract.
            log.warning(
                "Could not reach robots.txt for %s: %s. "
                "Allowing crawl.",
                origin,
                exc,
            )

            self._robots[origin] = None
            return True

    def _wait_turn(self, host: str) -> None:
        """Wait until this host's minimum request gap has passed."""

        now = time.monotonic()
        last_request = self._last_request.get(host)

        if last_request is not None:
            elapsed = now - last_request
            remaining = self.policy.delay_seconds - elapsed

            if remaining > 0:
                time.sleep(remaining)

        # Record the time immediately before the request.
        self._last_request[host] = time.monotonic()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _retry_after_seconds(
        self,
        response: httpx.Response,
        attempt: int,
    ) -> float:
        """Return the server-requested retry delay or exponential backoff."""

        retry_after = response.headers.get("Retry-After")

        if retry_after:
            # Retry-After can be either seconds or an HTTP date.
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_date = parsedate_to_datetime(retry_after)

                    if retry_date.tzinfo is None:
                        retry_date = retry_date.replace(
                            tzinfo=timezone.utc
                        )

                    now = datetime.now(timezone.utc)

                    return max(
                        0.0,
                        (retry_date - now).total_seconds(),
                    )

                except (TypeError, ValueError, OverflowError):
                    pass

        # No usable Retry-After header.
        # attempt 0 → 1 second
        # attempt 1 → 2 seconds
        # attempt 2 → 4 seconds
        return 2**attempt

    def _is_html(self, response: httpx.Response) -> bool:
        """Return True when the response looks like an HTML page."""

        content_type = response.headers.get("Content-Type", "").lower()

        return (
            "text/html" in content_type
            or "application/xhtml+xml" in content_type
            or content_type == ""
        )

    # ------------------------------------------------------------------
    # fetching
    # ------------------------------------------------------------------

    def fetch(self, url: str) -> RawPage | None:
        """GET an HTML page and return a RawPage.

        Ordinary skips such as robots denial, 404 and non-HTML responses
        return None.

        Network errors and unexpected failures are raised so the pipeline
        can record them as crawl errors.
        """

        if not self.allowed(url):
            log.info("Robots.txt disallowed: %s", url)
            return None

        host = urlsplit(url).netloc.lower()

        for attempt in range(self.policy.max_retries + 1):
            self._wait_turn(host)

            started = time.monotonic()

            try:
                response = self.client.get(url)

            except httpx.HTTPError:
                log.exception("HTTP error while fetching %s", url)
                raise

            elapsed_ms = int((time.monotonic() - started) * 1000)

            # Retry temporary server-side failures.
            if response.status_code in RETRYABLE_STATUSES:
                if attempt >= self.policy.max_retries:
                    log.warning(
                        "Giving up after %d attempts: %s → HTTP %s",
                        attempt + 1,
                        url,
                        response.status_code,
                    )
                    return None

                delay = self._retry_after_seconds(response, attempt)

                log.warning(
                    "Retrying %s after HTTP %s in %.1f seconds",
                    url,
                    response.status_code,
                    delay,
                )

                time.sleep(delay)
                continue

            # Never retry 404.
            if response.status_code == 404:
                log.info("404: %s", url)
                return None

            # Other unsuccessful HTTP statuses are ordinary skips.
            if response.status_code >= 400:
                log.warning(
                    "Skipping %s because server returned HTTP %s",
                    url,
                    response.status_code,
                )
                return None

            # fetch() is only for HTML.
            if not self._is_html(response):
                log.info(
                    "Skipping non-HTML URL from fetch(): %s (%s)",
                    url,
                    response.headers.get("Content-Type", ""),
                )
                return None

            # Check Content-Length before reading the body.
            content_length = response.headers.get("Content-Length")

            if content_length:
                try:
                    if int(content_length) > self.policy.max_bytes:
                        log.warning(
                            "HTML response too large: %s (%s bytes)",
                            url,
                            content_length,
                        )
                        return None
                except ValueError:
                    pass

            # httpx has already buffered normal responses here.
            # The Content-Length check protects the common case.
            content = response.content

            if len(content) > self.policy.max_bytes:
                log.warning(
                    "HTML response exceeded max_bytes: %s (%d bytes)",
                    url,
                    len(content),
                )
                return None

            encoding = response.encoding or "utf-8"
            html = content.decode(encoding, errors="replace")

            return RawPage(
                url=str(response.url),
                status=response.status_code,
                html=html,
                headers=dict(response.headers),
                fetched_at=datetime.now(timezone.utc),
                elapsed_ms=elapsed_ms,
            )

        return None

    def fetch_asset(self, url: str) -> RawAsset | None:
        """Download a non-HTML file without exceeding the asset size limit."""

        if not self.allowed(url):
            log.info("Robots.txt disallowed asset: %s", url)
            return None

        host = urlsplit(url).netloc.lower()

        for attempt in range(self.policy.max_retries + 1):
            self._wait_turn(host)

            started = time.monotonic()

            try:
                with self.client.stream("GET", url) as response:

                    elapsed_ms = int(
                        (time.monotonic() - started) * 1000
                    )

                    if response.status_code in RETRYABLE_STATUSES:
                        if attempt >= self.policy.max_retries:
                            return None

                        delay = self._retry_after_seconds(
                            response,
                            attempt,
                        )

                        log.warning(
                            "Retrying asset %s after HTTP %s in %.1f seconds",
                            url,
                            response.status_code,
                            delay,
                        )

                        time.sleep(delay)
                        continue

                    if response.status_code == 404:
                        log.info("Asset 404: %s", url)
                        return None

                    if response.status_code >= 400:
                        log.warning(
                            "Skipping asset %s because server returned HTTP %s",
                            url,
                            response.status_code,
                        )
                        return None

                    content_length = response.headers.get(
                        "Content-Length"
                    )

                    if content_length:
                        try:
                            if (
                                int(content_length)
                                > self.policy.max_asset_bytes
                            ):
                                log.warning(
                                    "Asset too large: %s (%s bytes)",
                                    url,
                                    content_length,
                                )
                                return None
                        except ValueError:
                            pass

                    chunks: list[bytes] = []
                    total_bytes = 0

                    for chunk in response.iter_bytes():
                        total_bytes += len(chunk)

                        if (
                            total_bytes
                            > self.policy.max_asset_bytes
                        ):
                            log.warning(
                                "Asset exceeded max_asset_bytes: %s",
                                url,
                            )
                            return None

                        chunks.append(chunk)

                    content = b"".join(chunks)

                    return RawAsset(
                        url=str(response.url),
                        status=response.status_code,
                        content=content,
                        content_type=response.headers.get(
                            "Content-Type",
                            "",
                        ),
                        fetched_at=datetime.now(timezone.utc),
                        elapsed_ms=elapsed_ms,
                    )

            except httpx.HTTPError:
                log.exception(
                    "HTTP error while fetching asset %s",
                    url,
                )
                raise

        return None

    def close(self) -> None:
        """Close the reusable HTTP connection pool."""

        self.client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()