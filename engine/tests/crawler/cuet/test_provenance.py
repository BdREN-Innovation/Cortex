"""Where each document and each PDF came from.

Team B receives text and PDFs and has to be able to ask "where is this from?"
without reading the crawler. `source` answered only "api or browser", which is
a category rather than an origin: it never said WHICH endpoint built a document,
so a bad extraction could not be traced back to the payload that caused it.
"""

from __future__ import annotations

import json

from engine.crawler.cuet.merge import write_file_index, write_provenance

DOCS = [
    {"doc_id": "aaa", "title": "Civil Engineering",
     "canonical_url": "https://cuet.ac.bd/department/CE",
     "fetched_at": "2026-09-09T18:07:21Z",
     "html_path": "academic/departments/CE__aaa.html",
     "meta": {"source": "api", "section": "academic",
              "origin": "API /administrative-departments/{slug}",
              "portion": "academic", "owner": "Samonwita Sarker"}},
    {"doc_id": "bbb", "title": "A listing",
     "canonical_url": "https://cuet.ac.bd/news-events",
     "fetched_at": "2026-09-09T18:07:21Z",
     "html_path": "news-events/listing/x__bbb.html",
     "meta": {"source": "browser", "section": "news-events",
              "origin": "browser render (crawl4ai + Chromium)",
              "portion": "news-events", "owner": "Samonwita Sarker"}},
]

FILES = {
    "https://app.cuet.ac.bd/storage/Notices/one.pdf": {
        "url": "https://app.cuet.ac.bd/storage/Notices/one.pdf",
        "document_type": "notice",
        "linked_from": ["https://cuet.ac.bd/department/CE",
                        "https://cuet.ac.bd/news-events"]},
    "https://app.cuet.ac.bd/storage/Notices/orphan.pdf": {
        "url": "https://app.cuet.ac.bd/storage/Notices/orphan.pdf",
        "document_type": "notice",
        "linked_from": ["https://cuet.ac.bd/never-captured"]},
}


def _provenance(tmp_path):
    write_provenance(tmp_path, DOCS, FILES)
    return [json.loads(l) for l in
            (tmp_path / "_meta" / "provenance.jsonl").read_text(
                encoding="utf-8").splitlines()]


def _index(tmp_path):
    write_file_index(tmp_path, DOCS, FILES)
    return json.loads((tmp_path / "_files" / "index.json").read_text(encoding="utf-8"))


# -- documents --------------------------------------------------------------

def test_every_document_names_the_endpoint_it_came_from(tmp_path):
    """The point of the whole file. "api" is a category; this is an origin."""
    docs = [r for r in _provenance(tmp_path) if r["kind"] == "document"]
    assert docs[0]["origin"] == "API /administrative-departments/{slug}"
    assert "browser" in docs[1]["origin"]


def test_an_api_document_points_at_the_saved_payload(tmp_path):
    """So a disagreement is settled against the bytes, not by re-crawling."""
    docs = [r for r in _provenance(tmp_path) if r["kind"] == "document"]
    assert docs[0]["raw_payload"] == "_meta/api_dump.json"


def test_a_browser_document_points_at_its_own_html(tmp_path):
    """There is no API payload behind it; the saved render IS the evidence."""
    docs = [r for r in _provenance(tmp_path) if r["kind"] == "document"]
    assert docs[1]["raw_payload"] == docs[1]["content_path"]


def test_the_owner_travels_with_the_document(tmp_path):
    """A reader who finds something wrong needs to know who to ask."""
    docs = [r for r in _provenance(tmp_path) if r["kind"] == "document"]
    assert all(d["owner"] == "Samonwita Sarker" for d in docs)


# -- files ------------------------------------------------------------------

def test_a_pdf_resolves_to_the_documents_that_link_it(tmp_path):
    row = [r for r in _index(tmp_path) if r["url"].endswith("one.pdf")][0]
    assert [s["doc_id"] for s in row["sources"]] == ["aaa", "bbb"]
    assert row["sources"][0]["origin"] == "API /administrative-departments/{slug}"


def test_a_pdf_keeps_every_source_not_just_the_last(tmp_path):
    """The same circular is linked from a notice index, a department page and
    sometimes a profile. Keeping one would invent a relationship."""
    row = [r for r in _index(tmp_path) if r["url"].endswith("one.pdf")][0]
    assert len(row["sources"]) == 2


def test_the_original_linked_from_list_is_left_alone(tmp_path):
    """`sources` is additive. Anything already reading `linked_from` keeps
    working."""
    row = [r for r in _index(tmp_path) if r["url"].endswith("one.pdf")][0]
    assert row["linked_from"] == FILES[row["url"]]["linked_from"]


def test_a_link_to_no_document_is_named_rather_than_dropped(tmp_path):
    """An empty `sources` with no explanation reads like a bug."""
    row = [r for r in _index(tmp_path) if r["url"].endswith("orphan.pdf")][0]
    assert row["sources"] == []
    assert row["unresolved_links"] == ["https://cuet.ac.bd/never-captured"]


def test_download_state_is_recorded(tmp_path):
    row = [r for r in _index(tmp_path) if r["url"].endswith("one.pdf")][0]
    assert row["downloaded"] is False


def test_rebuilding_the_index_preserves_the_downloaded_fields(tmp_path):
    """The index is regenerated on every merge. Losing `local` and `bytes`
    would mean re-downloading 285 PDFs to get them back."""
    write_file_index(tmp_path, DOCS, FILES)
    path = tmp_path / "_files" / "index.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        row["local"] = "_files/x.pdf"
        row["bytes"] = 1234
    path.write_text(json.dumps(rows), encoding="utf-8")

    rebuilt = _index(tmp_path)
    assert all(r["local"] == "_files/x.pdf" for r in rebuilt)
    assert all(r["bytes"] == 1234 for r in rebuilt)
    assert all(r["downloaded"] is True for r in rebuilt)


def test_every_document_and_file_appears(tmp_path):
    rows = _provenance(tmp_path)
    assert sum(1 for r in rows if r["kind"] == "document") == len(DOCS)
    assert sum(1 for r in rows if r["kind"] == "file") == len(FILES)
