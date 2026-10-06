"""Pure-function tests. No network, no fixtures. Spec §10.

Every case here is a real property of cuet.ac.bd, not an invented example. Where
a test looks oddly specific it is pinning a fact from the spec, and the section
is cited so the next person can tell a deliberate assertion from an arbitrary one.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from engine.crawler.cuet import config
from engine.crawler.cuet.paths import (
    canonical, encode_slug, group_for_url, in_allowed_host, is_excluded_url,
    is_image_url, looks_like_file, page_id, page_path, safe_name, section_for_url,
)


# --------------------------------------------------------------------------
# canonical — spec §6.3
# --------------------------------------------------------------------------

def test_canonical_removes_fragment_and_trailing_slash():
    assert canonical("https://cuet.ac.bd/a/") == "https://cuet.ac.bd/a"
    assert canonical("https://cuet.ac.bd/a#section") == "https://cuet.ac.bd/a"


def test_canonical_collapses_double_slash():
    # Not hypothetical: the site's own string concatenation emits
    # app.cuet.ac.bd//storage/Notices/<hash>.pdf. Spec §4.7.
    assert canonical("https://cuet.ac.bd//a//b") == "https://cuet.ac.bd/a/b"
    assert (canonical("https://app.cuet.ac.bd//storage/Notices/6a66d4ebbeb68.pdf")
            == "https://app.cuet.ac.bd/storage/Notices/6a66d4ebbeb68.pdf")


def test_canonical_drops_default_port():
    assert canonical("https://cuet.ac.bd:443/a") == "https://cuet.ac.bd/a"
    assert canonical("http://cuet.ac.bd:80/a") == "http://cuet.ac.bd/a"


def test_canonical_keeps_non_default_port():
    assert canonical("https://cuet.ac.bd:8443/a") == "https://cuet.ac.bd:8443/a"


def test_canonical_lowercases_host_but_not_path():
    assert canonical("https://CUET.ac.bd/Department/CE") == "https://cuet.ac.bd/Department/CE"


def test_canonical_distinguishes_cse_from_CE():
    # Spec §4.1: these are two different pages. Lowercasing the path merges them.
    assert canonical("https://cuet.ac.bd/department/cse") != \
           canonical("https://cuet.ac.bd/department/CE")


def test_canonical_collapses_bare_root_to_no_path():
    # The page links both forms in different blocks. Spec §6.3.
    assert canonical("https://library.cuet.ac.bd/") == "https://library.cuet.ac.bd"
    assert canonical("https://library.cuet.ac.bd") == "https://library.cuet.ac.bd"


def test_canonical_preserves_query_string():
    url = "https://api.cuet.ac.bd/api/v1/home-parameters?academic_headers=1"
    assert canonical(url) == url


# --------------------------------------------------------------------------
# page_id — spec §6.4
# --------------------------------------------------------------------------

def test_page_id_is_stable_across_processes():
    """Catches an accidental use of hash(), which is randomised per process.

    Run in a genuinely fresh interpreter — asserting twice in THIS process would
    pass even with hash(), which is the whole bug. Spec §6.4.
    """
    url = "https://cuet.ac.bd/department/cse"
    here = page_id(url)
    code = (
        "from engine.crawler.cuet.paths import page_id;"
        f"print(page_id({url!r}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == here


def test_page_id_matches_engine_contracts_make_doc_id():
    """The scraper's id must BE the engine's id, not merely resemble it.

    Team C's golden dataset references these hashes as relevant_doc_ids.
    Spec §12, and evaluation/README.md §4.
    """
    from engine.contracts.documents import make_doc_id
    url = "https://cuet.ac.bd/department/cse/"
    assert page_id(url) == make_doc_id(canonical(url))


def test_page_id_is_16_hex_chars():
    pid = page_id("https://cuet.ac.bd/")
    assert len(pid) == 16
    assert all(c in "0123456789abcdef" for c in pid)


# --------------------------------------------------------------------------
# safe_name — spec §6.5
# --------------------------------------------------------------------------

def test_safe_name_strips_traversal():
    assert ".." not in safe_name("../../etc/passwd")
    assert ".." not in safe_name("%2e%2e%2f%2e%2e%2fetc")


def test_safe_name_percent_decodes_before_sanitising():
    # admissioncuet.ac.bd serves percent-encoded filenames. Spec §4.7.
    got = safe_name("Department%20Allocation%20-%20KA%20(8.04.2026).pdf")
    assert got.endswith(".pdf")
    assert "%" not in got and " " not in got


def test_safe_name_handles_spaces_and_parentheses():
    # A real filename from /storage/Downloads/. Spec §4.7.
    got = safe_name("Teacher List of CUET-2026 (26.07.2026).pdf")
    assert got.endswith(".pdf")
    assert " " not in got and "(" not in got


def test_safe_name_caps_length_and_keeps_extension():
    got = safe_name("x" * 400 + ".pdf")
    assert len(got) <= config.MAX_NAME_LENGTH
    assert got.endswith(".pdf")


def test_safe_name_empty_falls_back_to_index():
    assert safe_name("") == "index"
    assert safe_name("...") == "index"
    assert safe_name("___") == "index"


# --------------------------------------------------------------------------
# encode_slug — spec §4.2
# --------------------------------------------------------------------------

@pytest.mark.parametrize("slug", [
    "architecture-&-planning",
    "electrical-&-computer-engineering",
    "science-&-technology",
    "l&e",                      # the Legal & Estate SECTION, found 2026-09-08
])
def test_encode_slug_handles_ampersand(slug):
    got = encode_slug(slug)
    assert "&" not in got
    assert "%26" in got


def test_encode_slug_does_not_leave_slashes():
    # A slug is one path segment. quote()'s default would leave "/" alone.
    assert "/" not in encode_slug("a/b")


# --------------------------------------------------------------------------
# section and group — spec §6.1, §6.5
# --------------------------------------------------------------------------

def test_section_for_url_exact_before_prefix():
    # /notices/noc is `exact` in top-bar. Part 2 adds a `notices` section with
    # the broader prefix /notices/, and exact must still win. Part 2 §12.1.
    assert section_for_url("https://cuet.ac.bd/notices/noc") == "top-bar"


def test_section_for_url_host_rule_wins():
    assert section_for_url("https://admissioncuet.ac.bd/about-us") == "admission"


def test_section_for_url_longest_prefix_wins():
    assert section_for_url("https://cuet.ac.bd/department/cse") == "academic"
    assert section_for_url("https://cuet.ac.bd/student/organizations") == "home"


def test_unmatched_url_goes_to_unsorted():
    # Must NOT be silently swallowed by a catch-all. Spec §6.1.
    assert section_for_url("https://cuet.ac.bd/totally-unknown-route") == "_unsorted"


def test_homepage_is_home_not_unsorted():
    assert section_for_url("https://cuet.ac.bd/") == "home"


def test_group_for_url():
    assert group_for_url("https://cuet.ac.bd/department/cse") == "departments"
    assert group_for_url("https://cuet.ac.bd/news/205") == "news"
    assert group_for_url("https://admissioncuet.ac.bd/about-us") == "admissioncuet"


# --------------------------------------------------------------------------
# page_path — spec §6.5
# --------------------------------------------------------------------------

def test_page_path_distinguishes_case_only_slugs_on_case_insensitive_fs():
    """The exact collision spec §4.1 warns about.

    The API reports the institute slug as `IICT`; the site footer links
    `/institutes/iict`. On Windows or macOS those two filenames are the same
    file unless the id8 suffix differs.
    """
    a = page_path("https://cuet.ac.bd/institutes/IICT", "html")
    b = page_path("https://cuet.ac.bd/institutes/iict", "html")
    assert a != b
    assert str(a).lower() != str(b).lower()


def test_page_path_two_segment_slug_for_department_subpages():
    p = page_path("https://cuet.ac.bd/department/cse/contact", "html")
    assert p.name.startswith("cse__contact__")


def test_page_path_no_traversal_and_within_length():
    p = page_path("https://cuet.ac.bd/a/../../../etc/passwd", "html")
    assert ".." not in str(p)
    assert len(p.name) <= config.MAX_NAME_LENGTH + 8


# --------------------------------------------------------------------------
# exclusion — spec §4.6, §6.2
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://app.cuet.ac.bd/storage/News/abc123.jpg",
    "https://app.cuet.ac.bd/storage/Student-Organization/abc.png",
    "https://app.cuet.ac.bd/storage/Student-Halls/abc.jpg",
    "https://app.cuet.ac.bd/storage/Admins/6a0de161a6d7f.jpg",
    "https://app.cuet.ac.bd/storage/General-Settings/abc.png",
    "https://app.cuet.ac.bd/storage/Photo-Galleries/68d18d96d8100.png",
    # The fourth host, found 2026-09-08. Arrives inside JSON, not HTML.
    "https://api.cuet.ac.bd/storage/Administrative-Departments/6656f2966468f.jpg",
    "https://cuet.ac.bd/assets/images/logo.png",
    "https://cuet.ac.bd/og.jpeg",
    "https://cuet.thetork.com/assets/images/campus-img-2.png",
])
def test_all_image_hosts_excluded(url):
    assert is_image_url(url), url
    assert is_excluded_url(url), url


def test_exclude_patterns_reject_php():
    assert is_excluded_url("https://www.cuet.ac.bd/dep_cse.php")


def test_exclude_hosts_reject_vendor_and_login_domains():
    assert is_excluded_url("https://cuet.thetork.com/faculty")
    assert is_excluded_url("https://v2.cuet.ac.bd/")
    assert is_excluded_url("https://course.cuet.ac.bd/")


@pytest.mark.parametrize("url", [
    "https://cuet.ac.bd/assets/pdf/professor-list-26.07.2026.pdf",
    "https://app.cuet.ac.bd//storage/Notices/6a66d4ebbeb68.pdf",
    "https://app.cuet.ac.bd/storage/Downloads/CUET-logo-and-directions.zip",
])
def test_exclude_patterns_do_not_reject_documents(url):
    """The classic crawl-config mistake: a \\.pdf$ rule switches the whole
    document pipeline off with no error. Spec §6.2."""
    assert not is_excluded_url(url), url
    assert looks_like_file(url), url


def test_allowed_hosts_includes_the_api():
    assert in_allowed_host("https://api.cuet.ac.bd/api/v1/notices")


def test_the_alumni_host_is_now_allowed():
    """This assertion used to be the opposite, and the change is the point.

    Spec 13 Q9 left alumni.cuet.ac.bd out of scope pending a decision, so the
    host was excluded and the test pinned that. The decision was taken on
    2026-09-09 - its robots.txt is a 404 and its pages carry no robots meta,
    the same as the main site - and the host is now a portion of the corpus.
    """
    assert in_allowed_host("https://alumni.cuet.ac.bd/")
    assert in_allowed_host("https://api.cuet.thetork.com/api/v1/alumni-settings")


def test_the_vendor_staging_host_is_still_excluded():
    """`cuet.thetork.com` is a staging leak; `api.` and `app.` on that domain
    are the alumni site's live backend. Matching is exact, so allowing the
    latter must not quietly allow the former."""
    from engine.crawler.cuet.paths import is_excluded_url
    assert is_excluded_url("https://cuet.thetork.com/anything")
    assert not is_excluded_url("https://api.cuet.thetork.com/api/v1/alumnis")


# --------------------------------------------------------------------------
# render and content detection — spec §7.2, §3.3
# --------------------------------------------------------------------------

def test_empty_table_regex_matches_the_skeleton():
    """The exact body /departments returns without JavaScript. Spec §2."""
    html = "<table><tbody><tr><td></td><td></td></tr><tr><td></td></tr></tbody></table>"
    assert config.EMPTY_TABLE_RE.search(html)


def test_empty_table_regex_does_not_match_a_populated_table():
    html = "<table><tr><td>Computer Science &amp; Engineering</td></tr></table>"
    assert not config.EMPTY_TABLE_RE.search(html)


def test_double_escape_detection():
    """research_highlight and research_area store already-escaped HTML. Spec §3.3."""
    bad = "&lt;p&gt;The faculty publish a great deal.&lt;/p&gt;"
    good = "<p>The faculty publish a great deal.</p>"
    assert any(m in bad for m in config.DOUBLE_ESCAPE_MARKERS)
    assert not any(m in good for m in config.DOUBLE_ESCAPE_MARKERS)


# --------------------------------------------------------------------------
# notice filtering — spec §3.6
# --------------------------------------------------------------------------

def test_notice_filter_matches_title_not_slug():
    """/notices returns `notice_type_title` ("Offices Orders/NOC"); /notice-types
    carries slugs ("noc"). They are different strings and neither is derivable
    from the other, so filtering on the wrong one silently yields zero notices.
    """
    assert "Offices Orders/NOC" in config.NOTICE_TYPES_IN_SCOPE
    assert "noc" not in config.NOTICE_TYPES_IN_SCOPE


def test_notice_scope_covers_the_three_in_scope_types():
    assert set(config.NOTICE_TYPES_IN_SCOPE) == {
        "Offices Orders/NOC",
        "Scholarship & Financial Aids",
        "Academic Calender",     # their spelling, deliberately not corrected
    }


# --------------------------------------------------------------------------
# config sanity
# --------------------------------------------------------------------------

def test_no_id_enumeration_ranges_survive():
    """Spec §4.9: deleted, and must not be reintroduced."""
    assert not hasattr(config, "NEWS_ID_RANGE")
    assert not hasattr(config, "EVENT_ID_RANGE")


def test_document_key_survives_canonicalisation():
    """Regression: a #fragment key collapsed 22 notice documents onto 3 ids.

    page_id() canonicalises before hashing and canonical() strips fragments
    (spec §6.3), so `...#part-2` and `...#part-3` hash identically. Query
    parameters survive, which is why the synthetic keys use `?_part=`.
    """
    base = "https://cuet.ac.bd/notices/noc"
    assert page_id(f"{base}#part-1") == page_id(f"{base}#part-2")   # the bug
    assert page_id(f"{base}?_part=1") != page_id(f"{base}?_part=2")  # the fix


def test_notice_scope_carries_a_real_listing_route():
    """canonical_url is what a citation shows a reader, so it must resolve.

    An earlier version emitted /notices/detail/<id>, which does not exist on
    this site and would 404 for anyone who clicked it.
    """
    for section, route in config.NOTICE_TYPES_IN_SCOPE.values():
        assert section in config.SECTIONS or section == "_unsorted"
        assert route.startswith("/notices/")
        assert "detail" not in route


def test_delay_is_polite():
    assert config.DELAY >= 1.5
    assert 404 not in config.RETRY_STATUSES
    assert 403 not in config.RETRY_STATUSES


def test_user_agent_carries_a_real_contact_address():
    """Spec §7.4 and the §10 definition of done.

    cuet.ac.bd serves no robots.txt, so the site has no way to state limits to
    us. The User-Agent is the only channel it has to reach whoever is running
    this, which makes a placeholder address worse here than on a site that
    publishes rules.
    """
    assert "REPLACE_ME" not in config.USER_AGENT
    assert "example.com" not in config.USER_AGENT
    assert "@" in config.CONTACT and "." in config.CONTACT.split("@")[-1]
    assert config.CONTACT in config.USER_AGENT


def test_file_extensions_contain_no_images():
    assert not any(e in config.FILE_EXTENSIONS
                   for e in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"))
