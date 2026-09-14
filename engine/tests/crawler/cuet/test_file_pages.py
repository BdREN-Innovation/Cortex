"""Downloaded files are captures too, so each one gets a pages.jsonl row.

The row's `content_path` points at the file in `_files/` and its `parent_url`
at the page that linked to it. Page rows from the shards must come out exactly
as they did before files were added.
"""

from __future__ import annotations

import json

from engine.contracts.documents import CrawledPage
from engine.crawler.cuet import merge
from engine.crawler.cuet.paths import page_id

PARENT = "https://cuet.ac.bd/downloads"
PDF_URL = "https://app.cuet.ac.bd/storage/Downloads/form.pdf"
DOC_URL = "https://app.cuet.ac.bd/storage/Downloads/form.doc"
MISSING_URL = "https://app.cuet.ac.bd/storage/Downloads/not-downloaded.pdf"
PLACEHOLDER_PDF = b"%PDF-1.4\n% placeholder for tests\n%%EOF\n"


def _page(pid: str) -> dict:
    return {
        "page_id": pid, "url": f"https://cuet.ac.bd/{pid}",
        "canonical_url": f"https://cuet.ac.bd/{pid}", "status": 200,
        "content_path": f"resources/{pid}.html", "fetched_at": "2026-09-08T00:00:00Z",
        "document_links": [PDF_URL], "source": "api", "section": "resources",
        "section_path": ["Downloads"],
    }


def _corpus(tmp_path, *, index: list[dict] | None) -> None:
    found = [{"url": u, "document_type": "download", "linked_from": [PARENT]}
             for u in (PDF_URL, DOC_URL, MISSING_URL)]
    (tmp_path / "_shards").mkdir()
    (tmp_path / "_shards" / "general.json").write_text(json.dumps({
        "portions": ["general"], "documents": [], "pages": [_page("downloads")],
        "found_files": found, "found_pages": [], "warnings": []}), encoding="utf-8")
    files = tmp_path / "_files"
    files.mkdir()
    (files / "abc__form.pdf").write_bytes(PLACEHOLDER_PDF)
    if index is not None:
        (files / "index.json").write_text(json.dumps(index), encoding="utf-8")


def _downloaded_index() -> list[dict]:
    return [
        {"url": PDF_URL, "local": "_files/abc__form.pdf", "bytes": len(PLACEHOLDER_PDF),
         "content_type": "application/pdf"},
        # Stage 5 records the bare filename when it resumes a download.
        {"url": DOC_URL, "local": "def__form.doc", "bytes": 10},
        {"url": MISSING_URL},
    ]


def _rows(tmp_path) -> list[dict]:
    return [json.loads(line) for line in
            (tmp_path / "pages.jsonl").read_text(encoding="utf-8").splitlines()]


def _file_row(tmp_path, url: str) -> dict:
    return next(r for r in _rows(tmp_path) if r["url"] == url)


def test_a_downloaded_file_gets_a_row_pointing_at_the_file(tmp_path):
    _corpus(tmp_path, index=_downloaded_index())
    merge.run(tmp_path)

    row = _file_row(tmp_path, PDF_URL)
    assert row["content_path"] == "_files/abc__form.pdf"
    assert (tmp_path / row["content_path"]).read_bytes() == PLACEHOLDER_PDF
    assert row["content_type"] == "application/pdf"
    assert row["page_id"] == page_id(PDF_URL)


def test_parent_url_is_the_page_that_linked_the_file(tmp_path):
    _corpus(tmp_path, index=_downloaded_index())
    merge.run(tmp_path)
    assert _file_row(tmp_path, PDF_URL)["parent_url"] == PARENT


def test_every_file_row_is_a_valid_crawled_page(tmp_path):
    _corpus(tmp_path, index=_downloaded_index())
    merge.run(tmp_path)
    for row in _rows(tmp_path):
        assert CrawledPage.from_dict(row).validate() == []


def test_a_file_that_was_never_downloaded_gets_no_row(tmp_path):
    _corpus(tmp_path, index=_downloaded_index())
    merge.run(tmp_path)
    assert MISSING_URL not in {r["url"] for r in _rows(tmp_path)}


def test_a_bare_local_filename_still_points_inside_files(tmp_path):
    _corpus(tmp_path, index=_downloaded_index())
    merge.run(tmp_path)
    row = _file_row(tmp_path, DOC_URL)
    assert row["content_path"] == "_files/def__form.doc"
    assert row["content_type"] == "application/msword"


def test_page_rows_are_unchanged_by_the_file_rows(tmp_path):
    """Whoever reads the HTML rows today must see the same rows tomorrow."""
    without = tmp_path / "without"
    with_files = tmp_path / "with"
    without.mkdir()
    with_files.mkdir()
    _corpus(without, index=None)
    _corpus(with_files, index=_downloaded_index())
    merge.run(without)
    merge.run(with_files)

    html = lambda rows: [r for r in rows if r["content_type"] == "text/html"]
    assert html(_rows(with_files)) == _rows(without)
    assert len(_rows(with_files)) == len(_rows(without)) + 2


def test_merge_is_repeatable_and_does_not_duplicate_rows(tmp_path):
    _corpus(tmp_path, index=_downloaded_index())
    merge.run(tmp_path)
    first = (tmp_path / "pages.jsonl").read_text(encoding="utf-8")
    merge.run(tmp_path)
    assert (tmp_path / "pages.jsonl").read_text(encoding="utf-8") == first


def test_report_and_manifest_count_the_file_rows(tmp_path):
    _corpus(tmp_path, index=_downloaded_index())
    report = merge.run(tmp_path)
    assert report["pages"] == 1
    assert report["file_pages"] == 2
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pages_written"] == 3


def test_a_file_sharing_a_page_id_with_a_page_is_skipped(tmp_path):
    _corpus(tmp_path, index=_downloaded_index())
    (tmp_path / "pages.jsonl").write_text("", encoding="utf-8")
    written = merge.write_file_pages(tmp_path, {page_id(PDF_URL)})
    assert written == 1
    assert PDF_URL not in {r["url"] for r in _rows(tmp_path)}
