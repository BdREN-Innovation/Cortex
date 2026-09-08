"""Content-building tests. Pure functions over synthetic payloads, no network.

The payload shapes here are copied from real 2026-09-08 responses, because the
bugs these catch were all shape bugs — the API did not look the way the spec
said it did.
"""

from __future__ import annotations

from cuet_scraper import config, content
from cuet_scraper.markdown import to_markdown, unescape_once


def _result():
    return content.Stage2Result()


# --------------------------------------------------------------------------
# /general-settings shape
# --------------------------------------------------------------------------

def test_setting_value_unwraps_the_id_key_value_envelope():
    """VERIFIED shape: every setting is {"id", "key", "value"}, NOT a bare
    string as spec §3.3 describes. Reading it as a string yielded 0 of 8 CMS
    documents and only a warning."""
    settings = {"about_us": {"id": 9, "key": "about_us", "value": "<p>Body</p>"}}
    assert content._setting_value(settings, "about_us") == "<p>Body</p>"


def test_setting_value_still_accepts_a_bare_string():
    assert content._setting_value({"about_us": "<p>Body</p>"}, "about_us") == "<p>Body</p>"


def test_setting_value_missing_key_is_empty_not_an_error():
    assert content._setting_value({}, "about_us") == ""


def test_build_cms_produces_a_document_per_key():
    dump = {"/general-settings": {"body": {
        key: {"id": i, "key": key, "value": f"<p>{key} body text here</p>"}
        for i, key in enumerate(config.CMS_CONTENT_KEYS)
    }}}
    result = _result()
    content.build_cms(dump, result)
    assert len(result.documents) == len(config.CMS_CONTENT_KEYS)
    assert {d.section for d in result.documents} == {"_cms"}


def test_build_cms_detects_and_unescapes_double_escaping():
    """research_highlight and research_area store already-escaped HTML.
    Spec §3.3 — and this is still true as of 2026-09-08."""
    dump = {"/general-settings": {"body": {"research_area": {
        "id": 22, "key": "research_area",
        "value": "<h2>Research Areas</h2><p>&lt;p&gt;Nested&lt;/p&gt;</p>",
    }}}}
    result = _result()
    content.build_cms(dump, result)
    doc = result.documents[0]
    assert doc.double_escaped
    assert "&lt;p&gt;" not in doc.html
    assert any(w.startswith("double_escaped:") for w in result.warnings)


# --------------------------------------------------------------------------
# Notices
# --------------------------------------------------------------------------

def _notice(nid, type_title, date="2026-09-01"):
    return {"id": nid, "title": f"Notice {nid}", "publish_date": date,
            "external_link": None,
            "pdf": f"https://app.cuet.ac.bd//storage/Notices/{nid:x}.pdf",
            "administrative_department_title": "Registrar",
            "notice_type_title": type_title}


def test_notices_become_index_documents_not_one_per_notice():
    """265 near-identical documents would embed as 265 near-identical vectors.
    See build_notices' docstring."""
    dump = {"/notices": {"body": {"data": [
        _notice(i, "Offices Orders/NOC") for i in range(1, 121)
    ]}}}
    result = _result()
    content.build_notices(dump, result)
    expected = -(-120 // config.NOTICES_PER_DOCUMENT)     # ceil
    assert len(result.documents) == expected
    # every notice's PDF is still recorded individually
    assert len(result.found_files) == 120


def test_notice_documents_have_distinct_keys_but_one_citation_url():
    dump = {"/notices": {"body": {"data": [
        _notice(i, "Offices Orders/NOC") for i in range(1, 121)
    ]}}}
    result = _result()
    content.build_notices(dump, result)
    assert len({d.key for d in result.documents}) == len(result.documents)
    assert {d.url for d in result.documents} == {"https://cuet.ac.bd/notices/noc"}


def test_out_of_scope_notices_are_recorded_but_not_downloaded():
    """Metadata is free — it arrives in the same response. Downloading 693 more
    PDFs is not. Two decisions, two switches. Part 2 §3.4."""
    dump = {"/notices": {"body": {"data": [
        _notice(1, "Offices Orders/NOC"),
        _notice(2, "Student Notices"),
    ]}}}
    result = _result()
    content.build_notices(dump, result)
    by_url = {r["category"]: r for r in result.found_files.values()}
    assert by_url["Offices Orders/NOC"]["download"] is True
    assert by_url["Student Notices"]["download"] is False


def test_notice_pdf_double_slash_is_canonicalised():
    """The site emits app.cuet.ac.bd//storage/. Without collapsing, the same
    file is stored twice. Spec §4.7."""
    dump = {"/notices": {"body": {"data": [_notice(1, "Offices Orders/NOC")]}}}
    result = _result()
    content.build_notices(dump, result)
    url = next(iter(result.found_files))
    assert "//storage" not in url
    assert url.startswith("https://app.cuet.ac.bd/storage/")


def test_different_out_of_scope_types_do_not_collide():
    """Every out-of-scope type shares the /notices/all-notice listing, so the
    type has to be part of the key."""
    dump = {"/notices": {"body": {"data": [
        _notice(1, "Student Notices"), _notice(2, "General Notices"),
    ]}}}
    result = _result()
    content.build_notices(dump, result)
    assert len({d.key for d in result.documents}) == 2


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------

def test_entity_body_uses_headed_sections_in_a_fixed_order():
    """Concatenating the fields bare loses the only signal telling a reader
    whether they are reading the department's description or its head's
    welcome message. See build_entities."""
    dump = {"_entity_details": {"cse": {"data": {
        "type": "academic", "title": "Computer Science & Engineering",
        "slug": "cse", "about": "<p>Founded 1998.</p>",
        "vision": "<p>To lead.</p>", "mission": "<p>To teach.</p>",
        "academicFaculty": {"title": "Electrical & Computer Eng."},
        "contacts": [{"purpose": "Office", "email": "a@b.c", "phone": "1"}],
    }}}}
    result = _result()
    content.build_entities(dump, result)
    doc = result.documents[0]
    text = to_markdown(doc.html)
    assert text.index("About") < text.index("Vision") < text.index("Mission")
    assert "Contact" in text


def test_entity_breadcrumb_comes_from_academic_faculty():
    """academicFaculty.title IS the section_path level — no join against
    /administrative-academic-faculties needed. Spec §3.5."""
    dump = {"_entity_details": {"cse": {"data": {
        "type": "academic", "title": "CSE", "slug": "cse",
        "about": "<p>Body.</p>",
        "academicFaculty": {"title": "Electrical & Computer Eng."},
    }}}}
    result = _result()
    content.build_entities(dump, result)
    assert result.documents[0].section_path == [
        "Academic", "Departments", "Electrical & Computer Eng.", "CSE"]


# --------------------------------------------------------------------------
# Link harvesting
# --------------------------------------------------------------------------

def test_harvest_drops_non_navigational_hrefs():
    """href="#" on every dropdown toggle, plus mailto:undefined and
    tel:undefined, which are the site's own bugs. Spec §4.8."""
    html = ('<a href="#">Toggle</a><a href="mailto:undefined">x</a>'
            '<a href="tel:undefined">y</a><a href="javascript:void(0)">z</a>')
    result = _result()
    content.harvest(html, config.SITE, result, linked_from="x")
    assert not result.found_pages and not result.found_files


def test_harvest_excludes_relative_image_paths_after_resolution():
    """CMS HTML holds relative image paths such as
    /assets/images/undergraduate.jpg, which only look like images once resolved
    against the base. Spec §4.6."""
    result = _result()
    content.harvest('<img src="/assets/images/undergraduate.jpg">',
                    config.SITE, result, linked_from="x")
    assert not result.found_files
    assert not any("undergraduate.jpg" in p for p in result.found_pages)


def test_harvest_excludes_the_vendor_domain():
    """cuet.thetork.com is left in CMS content by whoever authored it.
    Spec §4.11."""
    result = _result()
    content.harvest('<a href="https://cuet.thetork.com/faculty">Click</a>',
                    config.SITE, result, linked_from="x")
    assert not result.found_pages


def test_harvest_finds_documents_and_accumulates_linked_from():
    """The same PDF is linked from many pages; overwriting would lose every
    source but the last. Part 2 §12.3."""
    html = '<a href="/assets/pdf/professor-list.pdf">List</a>'
    result = _result()
    content.harvest(html, config.SITE, result, linked_from="page-a")
    content.harvest(html, config.SITE, result, linked_from="page-b")
    record = next(iter(result.found_files.values()))
    assert record["linked_from"] == ["page-a", "page-b"]


def test_harvest_finds_bare_document_urls_outside_anchors():
    result = _result()
    content.harvest("see https://app.cuet.ac.bd/storage/Downloads/x.pdf for more",
                    config.SITE, result, linked_from="x")
    assert any(u.endswith("x.pdf") for u in result.found_files)


# --------------------------------------------------------------------------
# Markdown conversion
# --------------------------------------------------------------------------

def test_markdown_keeps_alt_text_but_emits_no_image_link():
    """Alt text is prose sitting in HTML we already have; an image URL is
    something nothing downstream may fetch. Spec §4.6."""
    html = '<p><img src="https://x/y.jpg" alt="Seat growth by department"></p>'
    out = to_markdown(html)
    assert "Seat growth by department" in out
    assert "y.jpg" not in out


def test_markdown_drops_one_word_alt_as_chrome():
    assert "logo" not in to_markdown('<img src="/l.png" alt="logo">')


def test_markdown_renders_tables_as_grids():
    """The undergraduate prospectus is largely tables — a seat table flattened
    to prose is unusable. Spec §3.3."""
    html = "<table><tr><th>Dept</th><th>Seats</th></tr><tr><td>CSE</td><td>130</td></tr></table>"
    out = to_markdown(html)
    assert "| Dept | Seats |" in out
    assert "| CSE | 130 |" in out


def test_markdown_skips_script_and_style():
    out = to_markdown("<p>Real</p><script>var x=1;</script><style>p{}</style>")
    assert "Real" in out and "var x" not in out and "p{}" not in out


def test_markdown_preserves_bangla():
    """A mis-decode cannot be repaired downstream. Spec §4.12."""
    assert "চুয়েট" in to_markdown("<p>চুয়েট</p>")


def test_unescape_once_is_not_recursive():
    """Unescaping until stable would corrupt content that legitimately contains
    an escaped entity."""
    assert unescape_once("&amp;lt;p&amp;gt;") == "&lt;p&gt;"
