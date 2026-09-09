"""Faculty members: the 374 people, and what must never be written about them.

The endpoint behind these documents returns more than the website shows. Every
field the public profile page does not display is dropped before a document is
built, and these tests exist so that a later change to the merge logic cannot
quietly undo that.
"""

from __future__ import annotations

from engine.crawler.cuet import config
from engine.crawler.cuet.builders import academic
from engine.crawler.cuet.builders.base import Stage2Result

SITE = config.SITE

ROW = {
    "id": 6040, "slug": "dr-example-person", "name": "Dr. Example Person",
    "email": "example@cuet.ac.bd", "phone": "01710000000", "room_no": "302",
    "gender": "male", "employee_status": "running",
    "admin_type": "faculty_member",
    "administrative_department_title": "Civil Engineering",
    "admin_positions": [{"title": "Professor"}],
}

DETAIL = {"data": {
    "id": 6040, "name": "Dr. Example Person",
    # Everything in this block is nulled by the live API today. It is here so
    # the test fails loudly if the backend ever starts populating it.
    "nid": "1234567890", "date_of_birth": "1970-01-01", "blood_group": "B+",
    "father_name": "Someone Senior", "mother_name": "Someone Else",
    "permanent_address": "12 Private Road", "religion": "Islam",
    "file_no": "F-99", "prl_date": "2035-01-01", "district_id": 4,
    "profile": {"intro": "<p>Works on structures.</p>",
                "personal_email": "private@gmail.com",
                "address": "House 4, Private Lane"},
    "educations": [{"degree": "PhD", "institute": "Example University"}],
    "experiences": [{"designation": "Lecturer", "institute": "CUET"}],
    "researches": [{"title": "Concrete durability"}],
    "publications": [], "courses": [], "supervisions": [],
    "achievements_awards": [],
}}


def _dump(rows=None, details=None) -> dict:
    return {"_faculty": {"list": rows if rows is not None else [ROW],
                         "details": details if details is not None
                         else {ROW["slug"]: DETAIL}}}


def _build(dump) -> Stage2Result:
    result = Stage2Result()
    academic.build_faculty_members(dump, result)
    return result


# -- what must never be written --------------------------------------------

def test_the_identity_block_never_reaches_a_document():
    """National ID, date of birth, parents' names, religion, home address.

    The live API nulls all of these, so this test protects against a backend
    change rather than today's data. That is the point: by the time it starts
    returning them it is too late to notice by hand.
    """
    html = _build(_dump()).documents[0].html
    for leak in ("1234567890", "1970-01-01", "B+", "Someone Senior",
                 "Someone Else", "12 Private Road", "Islam", "F-99"):
        assert leak not in html, leak


def test_personal_email_and_home_address_are_dropped():
    """Both ARE populated for real people, and neither appears on the person's
    own public profile page. Verified against dr-sumit-majumder."""
    html = _build(_dump()).documents[0].html
    assert "private@gmail.com" not in html
    assert "Private Lane" not in html


def test_every_configured_private_field_is_honoured():
    """Pins the config list to behaviour, so it cannot become decorative."""
    detail = {"data": dict(DETAIL["data"])}
    for field in config.FACULTY_PRIVATE_FIELDS:
        detail["data"][field] = "SENTINEL"
    detail["data"]["profile"] = dict(DETAIL["data"]["profile"])
    for field in config.FACULTY_PRIVATE_PROFILE_FIELDS:
        detail["data"]["profile"][field] = "SENTINEL"
    html = _build(_dump(details={ROW["slug"]: detail})).documents[0].html
    assert "SENTINEL" not in html


def test_a_private_field_on_the_roster_row_is_dropped_too():
    """The roster and the detail are merged. Filtering only the detail would
    let the same field through by the other road."""
    row = dict(ROW, permanent_address="12 Private Road")
    html = _build(_dump(rows=[row])).documents[0].html
    assert "12 Private Road" not in html


# -- what must be kept ------------------------------------------------------

def test_the_work_contact_details_are_kept():
    """Office email, phone and room are shown on the public profile page, and
    they are most of what makes a staff directory worth having."""
    html = _build(_dump()).documents[0].html
    assert "example@cuet.ac.bd" in html
    assert "01710000000" in html
    assert "302" in html


def test_the_professional_record_becomes_prose():
    """Stored as text, not as serialised JSON, so retrieval can match on it."""
    html = _build(_dump()).documents[0].html
    assert "Works on structures" in html
    assert "PhD" in html and "Example University" in html
    assert "Concrete durability" in html
    assert "Lecturer" in html


def test_empty_sections_produce_no_empty_headings():
    """Publications, courses, supervisions and awards are all empty here."""
    html = _build(_dump()).documents[0].html
    for heading in ("Publications", "Courses", "Supervision",
                    "Achievements and awards"):
        assert f"<h2>{heading}</h2>" not in html


def test_the_document_records_that_fields_were_removed():
    """So a reader can tell the difference between "the site never had it" and
    "we chose not to store it"."""
    dropped = _build(_dump()).documents[0].extra["private_fields_dropped"]
    assert "nid" in dropped
    assert "profile.personal_email" in dropped


# -- shape ------------------------------------------------------------------

def test_the_citation_is_the_persons_own_profile_page():
    doc = _build(_dump()).documents[0]
    assert doc.url == f"{SITE}/profile/faculty-member/dr-example-person"
    assert doc.section == "academic"
    assert doc.group == "profiles"


def test_the_department_appears_in_the_breadcrumb():
    doc = _build(_dump()).documents[0]
    assert "Civil Engineering" in doc.section_path


def test_a_person_whose_detail_failed_still_gets_a_document():
    """The roster row alone carries name, department, position and work email.
    Losing the profile prose must not lose the person."""
    result = _build(_dump(details={ROW["slug"]: {"error": "Timeout"}}))
    assert len(result.documents) == 1
    assert "example@cuet.ac.bd" in result.documents[0].html


def test_a_missing_roster_warns_rather_than_raising():
    result = _build({"_faculty": {"error": "HTTP 500"}})
    assert result.documents == []
    assert "faculty_missing" in result.warnings


def test_a_row_without_a_slug_is_skipped_not_guessed():
    """The slug IS the citation URL. Inventing one produces a link that 404s."""
    result = _build(_dump(rows=[{"name": "No Slug", "email": "x@cuet.ac.bd"}]))
    assert result.documents == []


def test_every_person_gets_a_distinct_document():
    rows = [dict(ROW, slug=f"person-{i}", name=f"Person {i}") for i in range(5)]
    result = _build(_dump(rows=rows, details={}))
    assert len({d.url for d in result.documents}) == 5
