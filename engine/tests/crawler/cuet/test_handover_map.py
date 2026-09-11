"""The corpus README must describe the corpus that exists.

Its folder table was hand-maintained and drifted: it claimed 2 documents in a
folder holding 5, and had no row at all for the 374 faculty profiles. Counts are
now read off disk, and this test covers the half that still cannot be derived —
the mapping from a folder to the part of the website it came from.
"""

from __future__ import annotations

import json

from engine.crawler.cuet.handover import FOLDER_MAP, _folder_table


def _corpus(tmp_path, folders):
    for folder in folders:
        d = tmp_path / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / "doc.json").write_text(
            json.dumps({"page_id": "x" + folder.replace("/", "")}), encoding="utf-8")
    return tmp_path


def test_a_folder_missing_from_the_map_is_flagged_not_hidden(tmp_path):
    """The failure mode that matters. Dropping an unmapped folder would make the
    README look complete while a whole content type went undocumented."""
    table = _folder_table(_corpus(tmp_path, ["brand/new"]))
    assert "brand/new" in table
    assert "not in FOLDER_MAP" in table


def test_counts_come_from_disk(tmp_path):
    root = _corpus(tmp_path, ["academic/profiles"])
    for i in range(4):
        (root / "academic/profiles" / f"p{i}.json").write_text(
            json.dumps({"page_id": f"p{i}"}), encoding="utf-8")
    table = _folder_table(root)
    assert "| `academic/profiles/` | 5 |" in table


def test_the_generated_and_meta_folders_are_not_counted(tmp_path):
    root = _corpus(tmp_path, ["_shards", "_meta", "_files", "home"])
    table = _folder_table(root)
    for skipped in ("_shards", "_meta", "_files"):
        assert f"`{skipped}/`" not in table
    assert "| `home/` | 1 |" in table


def test_a_sidecar_without_a_page_id_is_not_a_document(tmp_path):
    root = tmp_path / "home"
    root.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps({"note": "not a document"}),
                                     encoding="utf-8")
    assert "| `home/` |" not in _folder_table(tmp_path)


def test_every_mapped_folder_names_a_place_on_the_site():
    """A row that does not say where to look is the row a reader skips."""
    for folder, (where, portion) in FOLDER_MAP.items():
        assert where.strip(), folder
        assert portion.strip(), folder


def test_the_readme_renders_with_braces_in_it(tmp_path):
    """The README carries JSON examples and `{slug}` route templates.

    It was built with str.format, which reads every brace as a field, so adding
    one example containing a JSON object made the whole merge stage raise
    KeyError after it had already written two files. Rendering it must not
    depend on the prose avoiding braces.
    """
    from engine.crawler.cuet.handover import write_readme
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "d.json").write_text(json.dumps({"page_id": "x"}),
                                              encoding="utf-8")
    write_readme(tmp_path)
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "{folder_table}" not in text
    assert '"kind": "document"' in text
    assert "| `home/` | 1 |" in text
