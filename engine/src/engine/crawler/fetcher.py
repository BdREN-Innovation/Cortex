"""HTTP with manners: robots.txt, a real User-Agent, rate limiting and retries.

Every request a crawl makes to a host — the robots.txt check, a rendered page,
a downloaded file — waits its turn on one `HostRateLimiter`, created when the
Fetcher starts. Nothing reaches a server around it.

A URL that is not fetched comes back as a `Skip` naming the reason, never as a
bare None, so the run can record why it is missing.

TEAM A OWNS THIS FILE.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
)

from engine.contracts.documents import RawAsset, RawPage
from engine.crawler import skips
from engine.crawler.skips import Skip

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
    concurrency: int = 3


class HostRateLimiter:
    """One request at a time per host, with `delay_seconds` of quiet between them.

    Each host has its own `asyncio.Lock`, held for the whole request. The gap is
    measured from when the previous request *finished*, so a slow response
    never eats into it, and a page render and a file download to the same host
    can never overlap. Different hosts do not wait on each other.
    """

    def __init__(self, delay_seconds: float):
        self.delay_seconds = delay_seconds
        self._locks: dict[str, asyncio.Lock] = {}
        self._finished_at: dict[str, float] = {}

    @asynccontextmanager
    async def slot(self, host: str) -> AsyncIterator[None]:
        """Hold this host's turn for the duration of one request."""

        host = host.lower()
        lock = self._locks.setdefault(host, asyncio.Lock())

        async with lock:
            finished_at = self._finished_at.get(host)

            if finished_at is not None:
                # Re-check after sleeping: the event loop may wake a timer a
                # clock tick early, and the gap is a promise, not an estimate.
                while (
                    remaining := self.delay_seconds
                    - (time.monotonic() - finished_at)
                ) > 0:
                    await asyncio.sleep(remaining)

            try:
                yield
            finally:
                self._finished_at[host] = time.monotonic()


class Fetcher:
    """One instance per crawl. Owns the per-host limiter and robots rules."""

    def __init__(
        self,
        policy: FetchPolicy | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.policy = policy or FetchPolicy()

        if self.policy.concurrency < 1:
            raise ValueError("concurrency must be at least 1")

        # `transport` exists so tests can stand in for the network.
        self.client = httpx.AsyncClient(
            headers={"User-Agent": self.policy.user_agent},
            timeout=self.policy.timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

        # robots.txt rules cached by origin. None means allow-all.
        self._robots: dict[str, RobotFileParser | None] = {}

        # Created once in start() and shared by every request of this crawl.
        self._limiter: HostRateLimiter | None = None

        self._browser_config = BrowserConfig(
            browser_type="chromium",
            headless=True,
            user_agent=self.policy.user_agent,
            verbose=False,
        )

        self._run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            # robots.txt is checked by allowed(), whose request goes through
            # the limiter. Crawl4AI's own check would fetch it around it.
            check_robots_txt=False,
            page_timeout=int(self.policy.timeout_seconds * 1000),
            wait_until="domcontentloaded",
            verbose=False,
        )

        # Persistent Crawl4AI browser for the lifetime of this Fetcher.
        self._crawler: AsyncWebCrawler | None = None

    # ------------------------------------------------------------------
    # politeness
    # ------------------------------------------------------------------

    async def allowed(self, url: str) -> bool:
        """Return True when robots.txt permits fetching this URL."""

        if not self.policy.obey_robots:
            return True

        parts = urlsplit(url)

        if not parts.scheme or not parts.netloc:
            log.warning("Invalid URL for robots check: %s", url)
            return False

        origin = f"{parts.scheme.lower()}://{parts.netloc.lower()}"

        if origin not in self._robots:
            await self._load_robots(origin)

        parser = self._robots[origin]

        if parser is None:
            return True

        return parser.can_fetch(self.policy.user_agent, url)

    async def _load_robots(self, origin: str) -> None:
        """Fetch and cache robots.txt for one origin, through the limiter."""

        limiter = await self._started_limiter()
        robots_url = f"{origin}/robots.txt"

        async with limiter.slot(urlsplit(origin).netloc):
            # Another task may have loaded it while this one waited its turn.
            if origin in self._robots:
                return

            try:
                started = time.monotonic()
                response = await self.client.get(robots_url)

            except (httpx.HTTPError, OSError) as exc:
                # If robots.txt cannot be reached, allow the crawl but log it.
                log.warning(
                    "Could not reach robots.txt for %s: %s. Allowing crawl.",
                    origin,
                    exc,
                )
                self._robots[origin] = None
                return

        log.debug(
            "robots.txt %s → %s in %.0f ms",
            robots_url,
            response.status_code,
            (time.monotonic() - started) * 1000,
        )

        # A missing robots.txt means allow-all.
        if response.status_code == 404:
            self._robots[origin] = None
            return

        if response.status_code >= 400:
            log.warning(
                "Could not read robots.txt for %s (HTTP %s); "
                "allowing crawl but recording the problem.",
                origin,
                response.status_code,
            )
            self._robots[origin] = None
            return

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        self._robots[origin] = parser

    async def _started_limiter(self) -> HostRateLimiter:
        """Return the crawl's limiter, starting the Fetcher if needed."""

        if self._limiter is None:
            await self.start()

        assert self._limiter is not None
        return self._limiter

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
                        retry_date = retry_date.replace(tzinfo=timezone.utc)

                    now = datetime.now(timezone.utc)

                    return max(0.0, (retry_date - now).total_seconds())

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

    async def fetch_many(self, urls: list[str]) -> list[RawPage | Skip]:
        """Render several HTML URLs with Crawl4AI.

        Returns one result per URL, in the order given: the page, or a `Skip`
        saying why it was not captured. Clean text extraction remains Team B's
        responsibility.
        """

        if not urls:
            return []

        # In normal crawl runs start() is called once by
        # `async with Fetcher(...)`. Keep lazy start for direct callers.
        await self.start()

        semaphore = asyncio.Semaphore(self.policy.concurrency)

        async def fetch_one(url: str) -> RawPage | Skip:
            async with semaphore:
                return await self._fetch_page(url)

        return list(await asyncio.gather(*(fetch_one(url) for url in urls)))

    async def fetch(self, url: str) -> RawPage | None:
        """Render one HTML URL through the Crawl4AI async path."""

        [result] = await self.fetch_many([url])
        return result if isinstance(result, RawPage) else None

    async def _fetch_page(self, url: str) -> RawPage | Skip:
        """Render one page, retrying the statuses worth retrying."""

        if not await self.allowed(url):
            log.info("Robots.txt disallowed: %s", url)
            return Skip(url=url, reason=skips.ROBOTS)

        limiter = await self._started_limiter()
        assert self._crawler is not None

        host = urlsplit(url).netloc

        for attempt in range(self.policy.max_retries + 1):
            started = time.monotonic()

            try:
                async with limiter.slot(host):
                    result = await self._crawler.arun(
                        url=url,
                        config=self._run_config,
                    )

            except Exception as exc:
                log.warning("Crawl4AI raised for %s: %r", url, exc)
                return Skip(url=url, reason=skips.FETCH_FAILED, detail=repr(exc))

            elapsed_ms = int((time.monotonic() - started) * 1000)
            status_code = int(getattr(result, "status_code", 0) or 0)

            if (
                status_code in RETRYABLE_STATUSES
                and attempt < self.policy.max_retries
            ):
                delay = 2**attempt
                log.warning(
                    "Retrying page %s after HTTP %s in %.1f seconds",
                    url,
                    status_code,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if status_code >= 400:
                log.warning(
                    "Skipping %s because server returned HTTP %s",
                    url,
                    status_code,
                )
                return Skip(
                    url=url,
                    reason=skips.http_reason(status_code),
                    status=status_code,
                    detail=f"after {attempt + 1} attempt(s)" if attempt else "",
                )

            if not getattr(result, "success", False):
                error_message = str(getattr(result, "error_message", "") or "")
                log.warning("Crawl4AI failed for %s: %s", url, error_message)
                return Skip(
                    url=url,
                    reason=skips.FETCH_FAILED,
                    status=status_code,
                    detail=error_message,
                )

            html = getattr(result, "html", "") or ""
            html_bytes = len(html.encode("utf-8", errors="replace"))

            if html_bytes > self.policy.max_bytes:
                log.warning(
                    "HTML exceeded max_bytes: %s (%d bytes)",
                    url,
                    html_bytes,
                )
                return Skip(
                    url=url,
                    reason=skips.TOO_LARGE,
                    status=status_code,
                    detail=f"{html_bytes} bytes > max_bytes {self.policy.max_bytes}",
                )

            return RawPage(
                url=str(getattr(result, "url", "") or url),
                status=status_code or 200,
                html=html,
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "X-Cortex-Fetcher": "crawl4ai",
                },
                fetched_at=datetime.now(timezone.utc),
                elapsed_ms=elapsed_ms,
            )

        # The last attempt always returns above.
        return Skip(url=url, reason=skips.FETCH_FAILED, detail="retries exhausted")

    async def fetch_asset(self, url: str) -> RawAsset | Skip:
        """Download a non-HTML file without exceeding the asset size limit."""

        if not await self.allowed(url):
            log.info("Robots.txt disallowed asset: %s", url)
            return Skip(url=url, reason=skips.ROBOTS)

        limiter = await self._started_limiter()
        host = urlsplit(url).netloc

        for attempt in range(self.policy.max_retries + 1):
            retry_delay = 0.0
            started = time.monotonic()

            try:
                async with limiter.slot(host):
                    async with self.client.stream("GET", url) as response:
                        status_code = response.status_code

                        if (
                            status_code in RETRYABLE_STATUSES
                            and attempt < self.policy.max_retries
                        ):
                            retry_delay = self._retry_after_seconds(
                                response,
                                attempt,
                            )

                        elif status_code >= 400:
                            log.warning(
                                "Skipping asset %s because server returned HTTP %s",
                                url,
                                status_code,
                            )
                            return Skip(
                                url=url,
                                reason=skips.http_reason(status_code),
                                status=status_code,
                                detail=(
                                    f"after {attempt + 1} attempt(s)" if attempt else ""
                                ),
                            )

                        else:
                            return await self._read_asset(response, url, started)

            except httpx.HTTPError as exc:
                log.warning("HTTP error while fetching asset %s: %r", url, exc)
                return Skip(url=url, reason=skips.FETCH_FAILED, detail=repr(exc))

            # Back off outside the host's slot, so the wait holds nobody up.
            log.warning(
                "Retrying asset %s after HTTP %s in %.1f seconds",
                url,
                status_code,
                retry_delay,
            )
            await asyncio.sleep(retry_delay)

        # The last attempt always returns above.
        return Skip(url=url, reason=skips.FETCH_FAILED, detail="retries exhausted")

    async def _read_asset(
        self,
        response: httpx.Response,
        url: str,
        started: float,
    ) -> RawAsset | Skip:
        """Stream a successful response body, stopping at max_asset_bytes."""

        limit = self.policy.max_asset_bytes
        content_length = response.headers.get("Content-Length")

        if content_length:
            try:
                if int(content_length) > limit:
                    log.warning("Asset too large: %s (%s bytes)", url, content_length)
                    return Skip(
                        url=url,
                        reason=skips.TOO_LARGE,
                        status=response.status_code,
                        detail=f"Content-Length {content_length} > max_asset_bytes {limit}",
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        total_bytes = 0

        async for chunk in response.aiter_bytes():
            total_bytes += len(chunk)

            if total_bytes > limit:
                log.warning("Asset exceeded max_asset_bytes: %s", url)
                return Skip(
                    url=url,
                    reason=skips.TOO_LARGE,
                    status=response.status_code,
                    detail=f"more than max_asset_bytes {limit}",
                )

            chunks.append(chunk)

        return RawAsset(
            url=str(response.url),
            status=response.status_code,
            content=b"".join(chunks),
            content_type=response.headers.get("Content-Type", ""),
            fetched_at=datetime.now(timezone.utc),
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Create the per-host limiter and start one persistent Chromium."""

        if self._limiter is None:
            self._limiter = HostRateLimiter(self.policy.delay_seconds)

        if self._crawler is not None:
            return

        crawler = AsyncWebCrawler(config=self._browser_config)
        await crawler.start()
        self._crawler = crawler

        log.info("Persistent Crawl4AI Chromium started")

    async def close_async(self) -> None:
        """Close persistent Chromium and the reusable HTTP client."""

        crawler = self._crawler
        self._crawler = None

        try:
            if crawler is not None:
                try:
                    await crawler.close()
                finally:
                    log.info("Persistent Crawl4AI Chromium closed")
        finally:
            await self.client.aclose()

    async def __aenter__(self) -> "Fetcher":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close_async()
