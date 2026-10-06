"""A crawl run's record of linked files, and of everything it left out.

Each downloaded file gets its own pages.jsonl row: `content_path` points at the
file in docs/ and `parent_url` at the page that linked it. A file that was not
downloaded goes to failed_documents.jsonl, and a page that was not captured to
skipped_pages.jsonl, each with the reason.

The network is a stand-in serving placeholder pages and a placeholder PDF.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from engine.contracts.documents import CrawledPage, RawAsset, RawPage, make_doc_id
from engine.crawler import pipeline, skips
from engine.crawler.fetcher import FetchPolicy
from engine.crawler.frontier import canonicalize
from engine.crawler.pipeline import AssetPolicy, CrawlConfig, crawl_async
from engine.crawler.skips import Skip

HOME = "https://site.test/"
NOTICES = "https://site.test/notices"
ABOUT = "https://site.test/about"
OFFSITE_PAGE = "https://other.test/page"
FORM_PDF = "https://site.test/files/form.pdf"
MISSING_PDF = "https://site.test/files/missing.pdf"
BIG_PDF = "https://site.test/files/big.pdf"
OFFSITE_PDF = "https://other.test/files/elsewhere.pdf"
PLACEHOLDER_PDF = (Path(__file__).parent / "fixtures" / "placeholder.pdf").read_bytes()


def _html(*hrefs: str) -> str:
    links = "".join(f'<a href="{href}">{href}</a>' for href in hrefs)
    return f'<html lang="en"><body>{links}</body></html>'


class FakeFetcher:
    """Serves placeholder pages and files, and records which files were asked for."""

    def __init__(self) -> None:
        self.pages = {
            HOME: _html(
                "/notices", "/about", OFFSITE_PAGE,
                "/files/form.pdf", "/files/missing.pdf", OFFSITE_PDF,
            ),
            # Links form.pdf a second time: it must be downloaded once.
            NOTICES: _html("/files/form.pdf", "/files/big.pdf"),
        }
        self.files: dict[str, RawAsset | Skip] = {
            FORM_PDF: RawAsset(
                url=FORM_PDF, status=200, content=PLACEHOLDER_PDF, content_type="application/pdf"
            ),
            MISSING_PDF: Skip(url=MISSING_PDF, reason=skips.HTTP_4XX, status=404),
            BIG_PDF: Skip(url=BIG_PDF, reason=skips.TOO_LARGE, status=200),
        }
        self.requested_files: list[str] = []

    async def __aenter__(self) -> "FakeFetcher":
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def fetch_many(self, urls: list[str]) -> list[RawPage | Skip]:
        return [
            RawPage(url=url, status=200, html=self.pages[url])
            if url in self.pages
            else Skip(url=url, reason=skips.HTTP_4XX, status=404)
            for url in urls
        ]

    async def fetch_asset(self, url: str) -> RawAsset | Skip:
        self.requested_files.append(url)
        return self.files[url]


def _crawl(tmp_path, monkeypatch, fake: FakeFetcher, **overrides) -> Path:
    monkeypatch.setattr(pipeline, "Fetcher", lambda policy: fake)
    config = CrawlConfig(
        site="site",
        seeds=[HOME],
        allowed_domains=["site.test"],
        max_depth=2,
        max_pages=overrides.get("max_pages", 10),
        fetch=FetchPolicy(delay_seconds=1.0),
        assets=AssetPolicy(max_documents=overrides.get("max_documents", 10)),
    )
    return asyncio.run(crawl_async(config, out_root=tmp_path, run_id="site-test"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def test_each_downloaded_file_gets_a_crawled_page_row(tmp_path, monkeypatch):
    fake = FakeFetcher()
    run_dir = _crawl(tmp_path, monkeypatch, fake)

    rows = _jsonl(run_dir / "pages.jsonl")
    [row] = [row for row in rows if row["url"] == FORM_PDF]

    assert row["parent_url"] == HOME
    assert row["content_path"] == "docs/files/0001-form.pdf"
    assert (run_dir / row["content_path"]).read_bytes() == PLACEHOLDER_PDF
    assert row["content_type"] == "application/pdf"
    assert row["page_id"] == make_doc_id(canonicalize(FORM_PDF))
    assert row["depth"] == 1
    assert row["meta"]["bytes"] == len(PLACEHOLDER_PDF)
    assert CrawledPage.from_dict(row).validate() == []

    # Linked from two pages, downloaded and recorded once.
    assert fake.requested_files.count(FORM_PDF) == 1
    assert _manifest(run_dir)["assets_saved"] == {FORM_PDF: row["content_path"]}

    # The HTML pages keep their own rows.
    page_rows = {row["url"]: row for row in rows if row["url"] in (HOME, NOTICES)}
    assert all(r["content_path"].startswith("raw/") for r in page_rows.values())
    assert all(r["parent_url"] == "" for r in page_rows.values())


def test_a_vague_content_type_falls_back_to_the_extension(tmp_path, monkeypatch):
    fake = FakeFetcher()
    fake.files[FORM_PDF] = RawAsset(
        url=FORM_PDF, status=200, content=PLACEHOLDER_PDF,
        content_type="application/octet-stream",
    )
    run_dir = _crawl(tmp_path, monkeypatch, fake)

    [row] = [row for row in _jsonl(run_dir / "pages.jsonl") if row["url"] == FORM_PDF]
    assert row["content_type"] == "application/pdf"


def test_files_that_could_not_be_downloaded_are_recorded(tmp_path, monkeypatch):
    fake = FakeFetcher()
    run_dir = _crawl(tmp_path, monkeypatch, fake)

    failed = {row["url"]: row for row in _jsonl(run_dir / "failed_documents.jsonl")}

    assert set(failed) == {MISSING_PDF, BIG_PDF, OFFSITE_PDF}
    assert (failed[MISSING_PDF]["reason"], failed[MISSING_PDF]["status"]) == (skips.HTTP_4XX, 404)
    assert failed[MISSING_PDF]["parent_url"] == HOME
    assert failed[BIG_PDF]["reason"] == skips.TOO_LARGE
    assert failed[BIG_PDF]["parent_url"] == NOTICES
    assert failed[OFFSITE_PDF]["reason"] == skips.OFF_SCOPE
    # Out of scope means never requested.
    assert OFFSITE_PDF not in fake.requested_files

    assert _manifest(run_dir)["documents_failed_by_reason"] == {
        skips.HTTP_4XX: 1, skips.TOO_LARGE: 1, skips.OFF_SCOPE: 1,
    }


def test_files_past_max_documents_are_recorded_not_requested(tmp_path, monkeypatch):
    fake = FakeFetcher()
    run_dir = _crawl(tmp_path, monkeypatch, fake, max_documents=1)

    failed = {row["url"]: row["reason"] for row in _jsonl(run_dir / "failed_documents.jsonl")}

    assert failed[MISSING_PDF] == skips.MAX_DOCUMENTS
    assert failed[BIG_PDF] == skips.MAX_DOCUMENTS
    assert fake.requested_files == [FORM_PDF]


def test_every_page_left_out_says_why(tmp_path, monkeypatch):
    run_dir = _crawl(tmp_path, monkeypatch, FakeFetcher())

    skipped = {row["url"]: row for row in _jsonl(run_dir / "skipped_pages.jsonl")}

    assert (skipped[ABOUT]["reason"], skipped[ABOUT]["status"]) == (skips.HTTP_4XX, 404)
    assert (skipped[ABOUT]["parent_url"], skipped[ABOUT]["depth"]) == (HOME, 1)
    assert skipped[OFFSITE_PAGE]["reason"] == skips.OFF_SCOPE
    assert skipped[OFFSITE_PAGE]["parent_url"] == HOME

    by_reason = _manifest(run_dir)["pages_skipped_by_reason"]
    assert by_reason[skips.HTTP_4XX] == 1
    assert by_reason[skips.OFF_SCOPE] == 1


def test_pages_still_queued_at_max_pages_are_recorded(tmp_path, monkeypatch):
    run_dir = _crawl(tmp_path, monkeypatch, FakeFetcher(), max_pages=1)

    skipped = {row["url"]: row for row in _jsonl(run_dir / "skipped_pages.jsonl")}

    assert skipped[NOTICES]["reason"] == skips.MAX_PAGES
    assert skipped[NOTICES]["parent_url"] == HOME
    assert skipped[ABOUT]["reason"] == skips.MAX_PAGES
