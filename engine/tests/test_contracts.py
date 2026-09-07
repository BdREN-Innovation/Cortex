from engine.contracts.documents import CleanDocument, content_hash, make_doc_id
from engine.contracts.jsonio import read_jsonl, write_jsonl


def make_doc(text="hello world", url="https://x.test/a"):
    return CleanDocument(
        doc_id=make_doc_id(url),
        source_url=url,
        canonical_url=url,
        title="A",
        text=text,
        content_hash=content_hash(text),
        fetched_at="2026-01-01T00:00:00+00:00",
    )


def test_doc_id_is_stable_across_calls():
    assert make_doc_id("https://x.test/a") == make_doc_id("https://x.test/a")
    assert make_doc_id("https://x.test/a") != make_doc_id("https://x.test/b")


def test_validate_catches_hash_drift():
    doc = make_doc()
    assert doc.validate() == []
    doc.text = "changed underneath"
    assert "content_hash does not match text" in doc.validate()


def test_jsonl_round_trip(tmp_path):
    path = tmp_path / "documents.jsonl"
    write_jsonl(path, [make_doc(url="https://x.test/1"), make_doc(url="https://x.test/2")])
    loaded = [CleanDocument.from_dict(row) for row in read_jsonl(path)]
    assert [d.canonical_url for d in loaded] == ["https://x.test/1", "https://x.test/2"]
    assert all(d.validate() == [] for d in loaded)
