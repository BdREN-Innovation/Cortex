"""How a shard is built, and the resume case that made it lose documents.

Stage 2 rebuilds a whole portion on every run, so its shard can be written from
the rows it just produced. Stage 4 cannot: it is resumable, and skips URLs it
has already captured. Writing its shard from one run's rows drops everything
captured before, silently.
"""

from __future__ import annotations

import json

from engine.crawler.cuet.builders.base import Stage2Result
from engine.crawler.cuet.content import rows_on_disk, write_shard


def _document(out, section, stem, url, *, source, text="Body text here."):
    """Write the .html/.md/.json triple the way write_document does."""
    folder = out / section
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.html").write_text(f"<p>{text}</p>", encoding="utf-8")
    (folder / f"{stem}.md").write_text(text, encoding="utf-8")
    (folder / f"{stem}.json").write_text(json.dumps({
        "url": url, "canonical_url": url, "page_id": stem.ljust(16, "0")[:16],
        "doc_key": url, "section": section, "group": "", "section_path": ["X"],
        "title": stem, "source": source, "status": 200,
        "fetched_at": "2026-09-09T00:00:00Z",
        "html_path": f"{section}/{stem}.html",
        "markdown_path": f"{section}/{stem}.md",
        "text_chars": len(text), "files": [],
    }, ensure_ascii=False), encoding="utf-8")


def test_rows_on_disk_finds_only_the_requested_source(tmp_path):
    _document(tmp_path, "home", "a", "https://cuet.ac.bd/a", source="browser")
    _document(tmp_path, "home", "b", "https://cuet.ac.bd/b", source="api")

    rows = rows_on_disk(tmp_path, source="browser")
    assert [r["url"] for r in rows] == ["https://cuet.ac.bd/a"]


def test_rows_on_disk_carries_the_text_back(tmp_path):
    """write_shard needs the markdown, which lives beside the sidecar."""
    _document(tmp_path, "home", "a", "https://cuet.ac.bd/a",
              source="browser", text="Real prose.")
    assert rows_on_disk(tmp_path, source="browser")[0]["_text"] == "Real prose."


def test_rows_on_disk_ignores_the_meta_shard_and_files_directories(tmp_path):
    """Those hold JSON that is not a document, and reading it as one would put
    the run record and the file index into the corpus."""
    for reserved in ("_meta", "_shards", "_files"):
        (tmp_path / reserved).mkdir(parents=True)
        (tmp_path / reserved / "x.json").write_text(
            json.dumps({"source": "browser", "markdown_path": "nope.md"}),
            encoding="utf-8")
    assert rows_on_disk(tmp_path, source="browser") == []


def test_rows_on_disk_skips_a_sidecar_whose_markdown_is_missing(tmp_path):
    """An interrupted write leaves the JSON without its markdown. Order is
    html, md, json precisely so that cannot happen, but a half-deleted corpus
    must not take the merge down with it."""
    _document(tmp_path, "home", "a", "https://cuet.ac.bd/a", source="browser")
    (tmp_path / "home" / "a.md").unlink()
    assert rows_on_disk(tmp_path, source="browser") == []


def test_rows_on_disk_survives_a_corrupt_sidecar(tmp_path):
    _document(tmp_path, "home", "a", "https://cuet.ac.bd/a", source="browser")
    (tmp_path / "home" / "broken.json").write_text("{not json", encoding="utf-8")
    assert len(rows_on_disk(tmp_path, source="browser")) == 1


def test_a_resumed_capture_keeps_the_pages_an_earlier_run_captured(tmp_path):
    """The regression this module exists for.

    Stage 4 skips what it has already captured, so a second run's `rows` hold
    only the new pages. Building the shard from those left three documents in
    the shard and six on disk — the earlier three were simply gone, with no
    error and no warning.
    """
    _document(tmp_path, "news-events", "listing", "https://cuet.ac.bd/news-events",
              source="browser")
    write_shard(tmp_path, ["browser"],
                rows_on_disk(tmp_path, source="browser"), Stage2Result())

    # A later run renders one more page and skips the first as already done.
    _document(tmp_path, "home", "index", "https://cuet.ac.bd", source="browser")
    write_shard(tmp_path, ["browser"],
                rows_on_disk(tmp_path, source="browser"), Stage2Result())

    shard = json.loads(
        (tmp_path / "_shards" / "browser.json").read_text(encoding="utf-8"))
    assert len(shard["documents"]) == 2
    assert {d["canonical_url"] for d in shard["documents"]} == {
        "https://cuet.ac.bd/news-events", "https://cuet.ac.bd"}


def test_the_shard_captured_at_is_stable_across_rebuilds(tmp_path):
    """A wall-clock build time made an unchanged rebuild produce a diff saying
    nothing, so it is derived from the content instead."""
    _document(tmp_path, "home", "a", "https://cuet.ac.bd/a", source="browser")
    rows = rows_on_disk(tmp_path, source="browser")

    write_shard(tmp_path, ["browser"], rows, Stage2Result())
    first = (tmp_path / "_shards" / "browser.json").read_bytes()
    write_shard(tmp_path, ["browser"], rows, Stage2Result())
    assert (tmp_path / "_shards" / "browser.json").read_bytes() == first


# --------------------------------------------------------------------------
# One shard per portion, whatever the invocation
# --------------------------------------------------------------------------

def _dump():
    """The smallest dump the four builders will accept without raising."""
    return {"_fetched_at": "2026-09-09T00:00:00Z"}


def test_a_full_run_writes_one_shard_per_portion_not_one_combined(tmp_path):
    """The bug: a run of all four wrote `a+b+c+d.json`.

    The four per-portion shards from earlier runs stayed on disk beside it, so
    `--stage merge` read the same documents twice and reported duplicate ids
    as warnings. A corpus assembled from files that disagree about how many
    documents exist is not a corpus.
    """
    from engine.crawler.cuet import content
    from engine.crawler.cuet.builders import portion_names

    content.run(_dump(), tmp_path)

    written = {p.stem for p in (tmp_path / "_shards").glob("*.json")}
    assert written == set(portion_names())
    assert not any("+" in name for name in written)


def test_naming_one_portion_writes_only_that_portions_shard(tmp_path):
    """The four-person property: nobody's run touches anybody else's file."""
    from engine.crawler.cuet import content

    content.run(_dump(), tmp_path, portions=["news-events"])

    assert {p.stem for p in (tmp_path / "_shards").glob("*.json")} \
        == {"news-events"}


def test_a_full_run_and_four_separate_runs_agree_byte_for_byte(tmp_path):
    """What is on disk must not depend on how the tool was invoked.

    Without this, whether the corpus is reproducible depends on whether the
    person who last ran it passed `--portion`, which is not a property anybody
    can check by reading the output.
    """
    from engine.crawler.cuet import content
    from engine.crawler.cuet.builders import portion_names

    together = tmp_path / "together"
    content.run(_dump(), together)
    one_by_one = tmp_path / "one-by-one"
    for name in portion_names():
        content.run(_dump(), one_by_one, portions=[name])

    for name in portion_names():
        a = (together / "_shards" / f"{name}.json").read_bytes()
        b = (one_by_one / "_shards" / f"{name}.json").read_bytes()
        assert a == b, name


def test_the_returned_result_still_describes_the_whole_run(tmp_path):
    """Files are written per portion; the return value is not.

    Callers and tests read `run()`'s result to learn what the run produced, so
    splitting the writes must not shrink what it reports.
    """
    from engine.crawler.cuet import content
    from engine.crawler.cuet.builders import portion_names

    whole = content.run(_dump(), tmp_path / "whole")
    parts = [content.run(_dump(), tmp_path / f"p-{n}", portions=[n])
             for n in portion_names()]

    assert len(whole.rows) == sum(len(p.rows) for p in parts)
    assert whole.found_pages == set().union(*(p.found_pages for p in parts))


def test_a_file_linked_from_two_portions_keeps_both_sources(tmp_path):
    """`linked_from` is unioned when portions are folded together.

    The same PDF is linked from pages in more than one portion. Overwriting
    would leave the corpus claiming it appears in one place only, which is the
    bug `harvest` already guards against within a portion.
    """
    from engine.crawler.cuet.content import _fold_into

    combined, portion = Stage2Result(), Stage2Result()
    combined.found_files["https://x/f.pdf"] = {
        "url": "https://x/f.pdf", "linked_from": ["https://cuet.ac.bd/a"]}
    portion.found_files["https://x/f.pdf"] = {
        "url": "https://x/f.pdf", "linked_from": ["https://cuet.ac.bd/b"]}

    _fold_into(combined, portion, rows=[])

    assert combined.found_files["https://x/f.pdf"]["linked_from"] == [
        "https://cuet.ac.bd/a", "https://cuet.ac.bd/b"]
