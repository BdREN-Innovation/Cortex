"""The Fetcher's per-host limiter, and the reasons it gives for not fetching.

No network and no browser: httpx gets a MockTransport, and Crawl4AI is replaced
by a stand-in that records when each render would have reached the host.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import httpx

from engine.contracts.documents import RawAsset, RawPage
from engine.crawler import fetcher as fetcher_module
from engine.crawler import skips
from engine.crawler.fetcher import FetchPolicy, Fetcher

HOST = "https://site.test"
OTHER_HOST = "https://other.test"
DELAY = 0.2
PLACEHOLDER_PDF = (Path(__file__).parent / "fixtures" / "placeholder.pdf").read_bytes()


class FakeCrawler:
    """Crawl4AI without a browser. `pages` maps URL -> (status, html)."""

    def __init__(self, hits: list[tuple[float, str]], pages: dict[str, tuple[int, str]]):
        self.hits = hits
        self.pages = pages

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def arun(self, url: str, config=None):
        self.hits.append((time.monotonic(), url))
        # A render takes time; the gap has to hold regardless.
        await asyncio.sleep(0.01)
        status, html = self.pages.get(url, (200, "<html><body>placeholder</body></html>"))
        return SimpleNamespace(
            url=url, success=status < 400, status_code=status, html=html, error_message=""
        )


def _fake_browser(monkeypatch, hits, pages=None) -> None:
    monkeypatch.setattr(
        fetcher_module, "AsyncWebCrawler", lambda config=None: FakeCrawler(hits, pages or {})
    )


def _transport(hits, routes: dict[str, tuple[int, bytes, dict]]) -> httpx.MockTransport:
    """Serve `routes` (URL -> status, body, headers); anything else is a 404."""

    def handle(request: httpx.Request) -> httpx.Response:
        hits.append((time.monotonic(), str(request.url)))
        status, body, headers = routes.get(str(request.url), (404, b"", {}))
        return httpx.Response(status, content=body, headers=headers)

    return httpx.MockTransport(handle)


def test_requests_to_one_host_are_spaced_by_delay_seconds(monkeypatch):
    hits: list[tuple[float, str]] = []
    _fake_browser(monkeypatch, hits)
    pdf = (200, PLACEHOLDER_PDF, {"Content-Type": "application/pdf"})
    routes = {f"{HOST}/files/a.pdf": pdf, f"{HOST}/files/b.pdf": pdf}
    policy = FetchPolicy(delay_seconds=DELAY, concurrency=3, max_retries=0)

    async def scenario():
        async with Fetcher(policy, transport=_transport(hits, routes)) as fetcher:
            limiter = fetcher._limiter
            # Page renders and file downloads, all at once, all to one host.
            results = await asyncio.gather(
                fetcher.fetch_many([f"{HOST}/one", f"{HOST}/two", f"{HOST}/three"]),
                fetcher.fetch_asset(f"{HOST}/files/a.pdf"),
                fetcher.fetch_asset(f"{HOST}/files/b.pdf"),
            )
            # A second batch uses the same limiter, so it remembers the first.
            await fetcher.fetch_many([f"{HOST}/four"])
            assert fetcher._limiter is limiter
            return results

    pages, first_pdf, second_pdf = asyncio.run(scenario())

    assert all(isinstance(page, RawPage) for page in pages)
    assert isinstance(first_pdf, RawAsset) and first_pdf.content == PLACEHOLDER_PDF
    assert isinstance(second_pdf, RawAsset)

    times = sorted(at for at, _url in hits)
    # robots.txt, four renders, two downloads.
    assert len(times) == 7
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    assert min(gaps) >= DELAY, gaps


def test_different_hosts_do_not_wait_for_each_other(monkeypatch):
    hits: list[tuple[float, str]] = []
    _fake_browser(monkeypatch, hits)
    policy = FetchPolicy(delay_seconds=1.0, concurrency=2, obey_robots=False)

    async def scenario():
        async with Fetcher(policy, transport=_transport(hits, {})) as fetcher:
            await fetcher.fetch_many([f"{HOST}/one", f"{OTHER_HOST}/one"])

    asyncio.run(scenario())

    (first, _), (second, _) = sorted(hits)
    assert second - first < 0.5


def test_a_url_not_fetched_comes_back_with_the_reason(monkeypatch):
    hits: list[tuple[float, str]] = []
    _fake_browser(
        monkeypatch,
        hits,
        pages={f"{HOST}/gone": (404, "<html>not found</html>"), f"{HOST}/huge": (200, "x" * 50)},
    )
    routes = {
        f"{HOST}/robots.txt": (200, b"User-agent: *\nDisallow: /private\n", {}),
        f"{HOST}/files/big.pdf": (200, b"x" * 100, {"Content-Type": "application/pdf"}),
    }
    policy = FetchPolicy(delay_seconds=0.0, max_bytes=40, max_asset_bytes=64, max_retries=0)

    async def scenario():
        async with Fetcher(policy, transport=_transport(hits, routes)) as fetcher:
            pages = await fetcher.fetch_many(
                [f"{HOST}/private/page", f"{HOST}/gone", f"{HOST}/huge"]
            )
            assets = [
                await fetcher.fetch_asset(f"{HOST}/private/form.pdf"),
                await fetcher.fetch_asset(f"{HOST}/files/missing.pdf"),
                await fetcher.fetch_asset(f"{HOST}/files/big.pdf"),
            ]
            return pages + assets

    results = asyncio.run(scenario())

    assert [(r.reason, r.status) for r in results] == [
        (skips.ROBOTS, 0),
        (skips.HTTP_4XX, 404),
        (skips.TOO_LARGE, 200),
        (skips.ROBOTS, 0),
        (skips.HTTP_4XX, 404),
        (skips.TOO_LARGE, 200),
    ]
    # Robots-disallowed URLs never reach the server.
    assert not any("/private/" in url for _at, url in hits)


def test_a_file_that_keeps_failing_is_a_5xx_after_the_retries(monkeypatch):
    hits: list[tuple[float, str]] = []
    _fake_browser(monkeypatch, hits)
    url = f"{HOST}/files/flaky.pdf"
    routes = {url: (503, b"", {"Retry-After": "0"})}
    policy = FetchPolicy(delay_seconds=0.0, max_retries=1, obey_robots=False)

    async def scenario():
        async with Fetcher(policy, transport=_transport(hits, routes)) as fetcher:
            return await fetcher.fetch_asset(url)

    result = asyncio.run(scenario())

    assert (result.reason, result.status) == (skips.HTTP_5XX, 503)
    assert [hit_url for _at, hit_url in hits] == [url, url]
