"""Placeholder pages, pattern dismissals, and whose gap is whose.

Three things the 2026-09-09 department sweep forced into the design, each one a
distinction the code previously could not make:

* a page that is **missing** versus one that **exists but is unpublished**,
* a URL dismissed **one by one** versus a family of 306 dismissed **by rule**,
* a coverage number for **the corpus** versus one for **a person**.

The first two are correctness. The third is the one that makes the Appendix B
check get read at all: a single corpus-wide gap count is a number four people
each attribute to somebody else.
"""

from __future__ import annotations

import json
import re

from engine.crawler.cuet import config
from engine.crawler.cuet.builders import PORTIONS, owner_of_url
from engine.crawler.cuet.capture import looks_not_found, looks_placeholder

SITE = config.SITE


# --------------------------------------------------------------------------
# Unpublished is not the same as missing
# --------------------------------------------------------------------------

def test_the_unpublished_curriculum_notice_is_a_placeholder():
    """The exact string 20 of the 36 department academic pages render."""
    body = ("Academic Curriculam data is in Progress!\n\n"
            "We're unable to locate the data you're looking for right now .")
    assert looks_placeholder(body)


def test_a_placeholder_is_not_a_404():
    """The distinction the whole feature exists for.

    Treating this as a 404 would discard a page that is genuinely on the site
    and genuinely says the curriculum is not published yet. That statement is
    true of CUET today and is worth having.
    """
    body = "Academic Curriculam data is in Progress!"
    assert looks_placeholder(body)
    assert not looks_not_found(body)


def test_a_404_is_not_a_placeholder():
    """And the reverse, so a widened placeholder marker can never quietly
    readmit the 18 fake documents that started all of this."""
    body = "Oops! Page not found. The page you were looking for could not be found."
    assert looks_not_found(body)
    assert not looks_placeholder(body)


def test_a_real_curriculum_page_is_neither():
    body = ("Undergraduate Study Programs. The Department of Mechanical "
            "Engineering forms the foundation for professional and personal "
            "development of the graduates.")
    assert not looks_placeholder(body)
    assert not looks_not_found(body)


def test_the_marker_is_case_insensitive():
    """The site's own capitalisation is inconsistent and it is not our job to
    depend on it."""
    assert looks_placeholder("ACADEMIC CURRICULAM DATA IS IN PROGRESS!")


def test_the_sites_misspelling_is_preserved_deliberately():
    """`Curriculam` is CUET's spelling, not a typo in this repo.

    Pinned because the obvious "fix" — correcting it to Curriculum — silently
    stops the marker matching anything at all.
    """
    assert any("curriculam" in marker for marker in config.PLACEHOLDER_MARKERS)


# --------------------------------------------------------------------------
# Dismissing a family of URLs by rule
# --------------------------------------------------------------------------

def _dismissed_by_pattern(path: str) -> bool:
    return any(re.compile(rx).search(path)
               for rx, _ in config.KNOWN_NOT_PLANNED_PATTERNS)


def test_a_department_subpage_is_dismissed():
    """306 URLs, 17 routes across 18 departments, all chrome."""
    for suffix in ("vision-mission", "class-routine", "contact", "officers",
                   "laboratories", "publications", "notice", "news-event",
                   "gallery", "others", "journals-conferences",
                   "testing-consultancy-service"):
        assert _dismissed_by_pattern(f"/department/CE/{suffix}"), suffix


def test_a_nested_department_subpage_is_dismissed_too():
    """Three of the 17 are two levels deep."""
    for suffix in ("faculty-members/current-faculties",
                   "faculty-members/former-faculties",
                   "research/ongoing-projects"):
        assert _dismissed_by_pattern(f"/department/cse/{suffix}"), suffix


def test_the_academic_pages_are_NOT_dismissed():
    """The negative lookahead earns its keep here.

    These 36 are real content and are captured. A pattern that swallowed them
    would hide a genuine gap behind a rule written for a different reason,
    which is the failure mode that makes blanket dismissals dangerous.
    """
    assert not _dismissed_by_pattern("/department/EEE/academic/postgraduate")
    assert not _dismissed_by_pattern("/department/EEE/academic/undergraduate")


def test_the_department_landing_page_is_NOT_dismissed():
    """It is the page that carries all the dismissed pages' content."""
    assert not _dismissed_by_pattern("/department/CE")


def test_the_pattern_does_not_reach_outside_departments():
    for path in ("/faculty/science-&-technology", "/institutes/IICT",
                 "/notices/noc", "/about/history"):
        assert not _dismissed_by_pattern(path), path


def test_every_pattern_carries_a_reason():
    """The rule the plain dict has always followed, applied to patterns.

    A regex silences every future URL that matches it, including ones nobody
    has looked at, so an unexplained one is worse than an unexplained URL.
    """
    for rx, reason in config.KNOWN_NOT_PLANNED_PATTERNS:
        assert reason.strip(), rx
        assert len(reason) > 30, f"{rx}: reason too thin to act on"


def test_every_pattern_compiles():
    for rx, _ in config.KNOWN_NOT_PLANNED_PATTERNS:
        re.compile(rx)


# --------------------------------------------------------------------------
# Whose gap is it
# --------------------------------------------------------------------------

def test_urls_are_attributed_to_the_portion_that_owns_them():
    assert owner_of_url(f"{SITE}/department/CE") == "academic"
    assert owner_of_url(f"{SITE}/notices/noc") == "notices"
    assert owner_of_url(f"{SITE}/news/42") == "news-events"
    assert owner_of_url(f"{SITE}/student/halls") == "general"


def test_a_bare_path_works_as_well_as_a_full_url():
    """The gap diff holds full URLs; a caller reading urls.txt has paths."""
    assert owner_of_url("/institutes/IICT") == "academic"


def test_an_unclaimed_url_is_reported_rather_than_guessed():
    """None is a finding, not a failure.

    An area no portion claims is one the four-way split missed, and silently
    assigning it to whichever portion sorts first would bury exactly that.
    """
    assert owner_of_url(f"{SITE}/some-area-nobody-divided-up") is None


def test_the_longest_prefix_wins():
    """So one portion can hold a sub-area of another's without ambiguity."""
    academic = next(p for p in PORTIONS if p.name == "academic")
    assert "/department" in academic.url_prefixes
    assert owner_of_url(f"{SITE}/department/CE/academic/postgraduate") == "academic"


def test_a_prefix_matches_only_on_a_path_boundary():
    """`/notice` must not claim `/noticeboard-vendor`, and `/news` must not
    claim `/newsletter`. Substring matching would do both."""
    assert owner_of_url(f"{SITE}/newsletter-signup") is None


def test_no_two_portions_claim_the_same_prefix():
    """Two owners for one prefix is a merge conflict waiting in the corpus,
    not just an ambiguous report."""
    seen: dict[str, str] = {}
    for portion in PORTIONS:
        for prefix in portion.url_prefixes:
            assert prefix not in seen, (
                f"{prefix} claimed by both {seen.get(prefix)} and {portion.name}")
            seen[prefix] = portion.name


def test_every_portion_claims_at_least_one_prefix():
    """A portion with no prefixes can never be credited with closing a gap,
    so its coverage silently reads as somebody else's."""
    for portion in PORTIONS:
        assert portion.url_prefixes, portion.name


# --------------------------------------------------------------------------
# Repairing metadata without touching the network
# --------------------------------------------------------------------------

def test_an_older_sidecar_gains_content_state_from_bytes_on_disk(tmp_path):
    """The property that makes adding a metadata field free.

    `content_state` did not exist when the 83 browser pages were captured.
    Recomputing it from the saved markdown is the same offline repair that
    fixed the HTML-entity bug for one second instead of 61 requests to a
    university's servers.
    """
    from engine.crawler.cuet.capture import _backfill_content_state

    sidecar = tmp_path / "page.json"
    sidecar.write_text(json.dumps({"url": "u", "source": "browser"}),
                       encoding="utf-8")
    row = {"url": "u", "source": "browser", "_json_path": sidecar,
           "_text": "Academic Curriculam data is in Progress!"}

    _backfill_content_state(row, tmp_path)

    assert row["content_state"] == "placeholder"
    assert json.loads(sidecar.read_text(encoding="utf-8"))["content_state"] \
        == "placeholder"


def test_a_published_page_is_labelled_published_not_left_blank(tmp_path):
    """Absent and "published" must not be the same state.

    A missing key means nobody has looked; "published" means somebody did and
    found content. Downstream can only filter on the difference if it exists.
    """
    from engine.crawler.cuet.capture import _backfill_content_state

    sidecar = tmp_path / "page.json"
    sidecar.write_text("{}", encoding="utf-8")
    row = {"_json_path": sidecar, "_text": "Undergraduate Study Programs."}
    _backfill_content_state(row, tmp_path)
    assert row["content_state"] == "published"


def test_rewriting_an_already_correct_sidecar_is_skipped(tmp_path):
    """So a rebuild of a settled corpus stays byte-identical.

    Without this the reharvest stage rewrites all 83 sidecars every run and
    every rebuild shows up as a diff, which trains people to ignore diffs.
    """
    from engine.crawler.cuet.capture import _backfill_content_state

    sidecar = tmp_path / "page.json"
    sidecar.write_text('{"content_state": "published", "kept": true}',
                       encoding="utf-8")
    before = sidecar.read_bytes()
    row = {"_json_path": sidecar, "_text": "Real content.",
           "content_state": "published"}
    _backfill_content_state(row, tmp_path)
    assert sidecar.read_bytes() == before


def test_the_private_keys_never_reach_the_sidecar(tmp_path):
    """`_text` is the whole page and `_json_path` is a Path object; writing
    either would bloat the file and break json.dumps respectively."""
    from engine.crawler.cuet.capture import _backfill_content_state

    sidecar = tmp_path / "page.json"
    sidecar.write_text("{}", encoding="utf-8")
    row = {"_json_path": sidecar, "_text": "Real content.", "url": "u"}
    _backfill_content_state(row, tmp_path)
    written = json.loads(sidecar.read_text(encoding="utf-8"))
    assert set(written) == {"url", "content_state"}
