"""The four-person split: portions, shards, and merging them back.

These are the tests that stop the parallel-work design from quietly rotting.
Every one of them describes a way four people collide, not a way the code is
untidy.
"""

from __future__ import annotations

import json

import pytest

from engine.crawler.cuet import merge
from engine.crawler.cuet.builders import PORTIONS, builders_for, portion_names


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------

def test_portion_names_are_unique():
    """Two portions sharing a name means one shard silently overwrites the other."""
    names = [p.name for p in PORTIONS]
    assert len(names) == len(set(names))


def test_every_builder_belongs_to_exactly_one_portion():
    """A builder in two portions runs twice and writes its documents twice.

    A builder in none never runs at all, which is the worse failure: the corpus
    comes out plausible and short, with nothing anywhere saying what is missing.
    """
    seen = [b for p in PORTIONS for b in p.builders]
    assert len(seen) == len(set(seen))


def test_no_portion_is_empty():
    assert all(p.builders for p in PORTIONS)


def test_every_portion_names_its_sections_and_its_part_of_the_site():
    """Both fields are what --list-portions prints, and what a new person reads."""
    for portion in PORTIONS:
        assert portion.sections, portion.name
        assert portion.site_areas, portion.name


def test_builders_for_none_returns_every_builder():
    assert len(builders_for(None)) == sum(len(p.builders) for p in PORTIONS)


def test_builders_for_selects_only_the_named_portion():
    academic = next(p for p in PORTIONS if p.name == "academic")
    assert builders_for(["academic"]) == academic.builders


def test_builders_for_is_registry_ordered_not_caller_ordered():
    """Two portions produce the same shard whichever order they were named in."""
    assert builders_for(["academic", "general"]) == builders_for(["general", "academic"])


def test_portion_names_matches_the_registry():
    assert portion_names() == tuple(p.name for p in PORTIONS)


# --------------------------------------------------------------------------
# Merging shards
# --------------------------------------------------------------------------

def _doc(doc_id: str, **over) -> dict:
    base = {
        "doc_id": doc_id, "source_url": f"https://cuet.ac.bd/{doc_id}",
        "canonical_url": f"https://cuet.ac.bd/{doc_id}", "title": doc_id,
        "text": "body", "content_hash": "h", "fetched_at": "2026-09-08T00:00:00Z",
        "section_path": ["X"], "html_path": f"x/{doc_id}.html", "lang": "en",
        "doc_type": "page", "meta": {}, "assets": [],
    }
    base.update(over)
    return base


def _page(page_id: str) -> dict:
    return {
        "page_id": page_id, "url": f"https://cuet.ac.bd/{page_id}",
        "canonical_url": f"https://cuet.ac.bd/{page_id}", "status": 200,
        "content_path": f"x/{page_id}.html", "fetched_at": "2026-09-08T00:00:00Z",
        "document_links": [], "source": "api", "section": "x", "section_path": ["X"],
    }


def _shard(tmp_path, name: str, payload: dict) -> None:
    shards = tmp_path / "_shards"
    shards.mkdir(exist_ok=True)
    (shards / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _empty(portion: str, **over) -> dict:
    payload = {"portions": [portion], "documents": [], "pages": [],
               "found_files": [], "found_pages": [], "warnings": []}
    payload.update(over)
    return payload


def test_merge_with_no_shard_directory_says_what_to_run(tmp_path):
    """An empty corpus and an unbuilt one look identical unless something says so."""
    with pytest.raises(merge.NoShardsError) as caught:
        merge.run(tmp_path)
    assert "--stage content" in str(caught.value)


def test_merge_refuses_a_corrupt_shard_rather_than_shrinking_the_corpus(tmp_path):
    """Skipping a bad shard would look exactly like a portion nobody has built."""
    (tmp_path / "_shards").mkdir()
    (tmp_path / "_shards" / "academic.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(merge.NoShardsError):
        merge.run(tmp_path)


def test_merge_combines_documents_from_every_shard(tmp_path):
    _shard(tmp_path, "academic", _empty(
        "academic", documents=[_doc("a1"), _doc("a2")],
        pages=[_page("a1"), _page("a2")]))
    _shard(tmp_path, "news-events", _empty(
        "news-events", documents=[_doc("n1")], pages=[_page("n1")]))

    report = merge.run(tmp_path)
    assert report["documents"] == 3
    assert report["shards"] == 2
    assert report["portions"] == ["academic", "news-events"]


def test_merged_documents_are_sorted_by_id_so_the_output_is_deterministic(tmp_path):
    """Two people merging the same shards must get byte-identical files.

    Without this, regenerating is not a real answer to a conflict, because
    every regeneration would produce a different diff.
    """
    _shard(tmp_path, "b", _empty("b", documents=[_doc("zz"), _doc("mm")]))
    _shard(tmp_path, "a", _empty("a", documents=[_doc("aa")]))
    merge.run(tmp_path)
    ids = [json.loads(line)["doc_id"]
           for line in (tmp_path / "documents.jsonl").read_text(
               encoding="utf-8").splitlines() if line.strip()]
    assert ids == ["aa", "mm", "zz"]


def test_merge_unions_linked_from_across_shards(tmp_path):
    """The same PDF is linked from several portions.

    Last shard wins would drop every source but one, and linked_from is what a
    citation uses to show a reader where a file came from.
    """
    pdf = "https://app.cuet.ac.bd/storage/Notices/x.pdf"
    _shard(tmp_path, "notices", _empty("notices", found_files=[
        {"url": pdf, "linked_from": ["https://cuet.ac.bd/notices/noc"],
         "download": True}]))
    _shard(tmp_path, "academic", _empty("academic", found_files=[
        {"url": pdf, "linked_from": ["https://cuet.ac.bd/department/cse"],
         "download": False}]))

    merge.run(tmp_path)
    files = json.loads(
        (tmp_path / "_meta" / "found_files.json").read_text(encoding="utf-8"))
    record = next(f for f in files if f["url"] == pdf)
    assert record["linked_from"] == ["https://cuet.ac.bd/department/cse",
                                     "https://cuet.ac.bd/notices/noc"]
    # One portion wanting the file is enough to want it.
    assert record["download"] is True


def test_merge_reports_a_document_claimed_by_two_portions(tmp_path):
    """Two builders producing one id means somebody has wandered into another
    person's slice. Silently keeping the last one read hides it."""
    _shard(tmp_path, "one", _empty("one", documents=[_doc("dup", title="A")]))
    _shard(tmp_path, "two", _empty("two", documents=[_doc("dup", title="B")]))
    report = merge.run(tmp_path)
    assert report["documents"] == 1
    assert report["warnings"] >= 1


def test_merge_records_which_portions_the_corpus_contains(tmp_path):
    """A corpus merged from three shards of four is incomplete, not broken.
    The manifest is the only place that stays true once the terminal is gone."""
    _shard(tmp_path, "academic", _empty(
        "academic", documents=[_doc("a")], pages=[_page("a")]))
    merge.run(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["portions"] == ["academic"]
