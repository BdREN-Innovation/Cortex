"""The alumni portion: what it captures, and the two things it must never do.

The alumni site shares a backend with cuet.ac.bd, so the risk here is not
missing content but capturing the SAME content twice under a second set of
URLs. And it is the only source in the corpus carrying personal contact
details, so the field-dropping rule needs a test that fails loudly if anybody
widens the endpoint list later.
"""

from __future__ import annotations

from engine.crawler.cuet import config
from engine.crawler.cuet.builders import alumni, owner_of_url
from engine.crawler.cuet.builders.base import Stage2Result
from engine.crawler.cuet.paths import section_for_url

SITE = config.ALUMNI_SITE


def _dump(**alumni_bodies) -> dict:
    """A dump shaped the way discover._fetch_alumni writes one."""
    # Keyed by the bare endpoint path, exactly as discover stores it: the
    # /api/v1 prefix lives in config.ALUMNI_API, not in Endpoint.path.
    return {"_alumni": {path: {"status": 200, "body": body}
                        for path, body in alumni_bodies.items()}}


def _build(fn, dump) -> Stage2Result:
    result = Stage2Result()
    fn(dump, result)
    return result


# -- privacy ---------------------------------------------------------------

PERSON = {
    "id": 5, "studentID": "18010134", "full_name": "Mr Alumni",
    "email": "someone@example.com", "phone": "01700000000",
    "address": "12 Example Road, Chattogram",
    "batch": "2017-18", "degree": "B.Sc. in Computer Science and Engineering",
    "administrative_department_title": "Computer Science & Engineering",
    "passing_year": 2024, "current_position": "Software Engineer",
    "country": "Bangladesh", "bio": "<p>A software engineer.</p>",
}


def test_contact_details_never_reach_a_document():
    """The rule that matters. A directory of graduates is the one place in this
    corpus where a leak would be somebody's home address, not a stale count."""
    result = _build(alumni.build_alumni_directory,
                    _dump(**{"/alumnis": {"data": [PERSON]}}))
    blob = " ".join(d.html for d in result.documents)
    assert "someone@example.com" not in blob
    assert "01700000000" not in blob
    assert "12 Example Road" not in blob


def test_the_useful_fields_survive():
    """Dropping the contact fields must not gut the record: degree, batch and
    department are exactly what a retrieval corpus is for."""
    result = _build(alumni.build_alumni_directory,
                    _dump(**{"/alumnis": {"data": [PERSON]}}))
    html = result.documents[0].html
    assert "2017-18" in html
    assert "Computer Science" in html
    assert result.documents[0].title == "Mr Alumni"


def test_the_dropped_field_list_is_recorded_on_the_document():
    """So a reader of the corpus can tell that something was removed, rather
    than assuming the site never had it."""
    result = _build(alumni.build_alumni_directory,
                    _dump(**{"/alumnis": {"data": [PERSON]}}))
    assert result.documents[0].extra["private_fields_dropped"] == list(
        config.ALUMNI_PRIVATE_FIELDS)


def test_every_private_field_name_is_actually_dropped():
    """Pins the config list to the behaviour: adding a name there must remove
    it, so the list cannot drift into being decorative."""
    row = dict(PERSON)
    for field in config.ALUMNI_PRIVATE_FIELDS:
        row.setdefault(field, "SENTINEL-" + field)
    result = _build(alumni.build_alumni_directory,
                    _dump(**{"/alumnis": {"data": [row]}}))
    assert "SENTINEL-" not in result.documents[0].html


# -- no second copy of the university's content ----------------------------

def test_the_shared_endpoints_are_not_in_the_alumni_endpoint_list():
    """The vendor host serves the university's own /news and /notices. Capturing
    them here would give one notice two citable URLs."""
    paths = {e.path for e in config.ALUMNI_ENDPOINTS}
    for shared in ("/news", "/notices", "/notice-types", "/download-types",
                   "/downloads", "/administrative-departments-mini-index"):
        assert shared not in paths


def test_alumni_urls_are_attributed_to_the_alumni_portion():
    """`/news/146` exists on both hosts and means different things. Attribution
    by path alone would file the alumni one under news-events."""
    assert owner_of_url(f"{SITE}/news/146") == "alumni"
    assert owner_of_url("https://cuet.ac.bd/news/146") == "news-events"


def test_alumni_pages_are_filed_under_their_own_section():
    """Routed by host, so the alumni /about does not land in the university's
    About folder."""
    assert section_for_url(f"{SITE}/about") == "alumni"
    assert section_for_url(f"{SITE}/news/146") == "alumni"
    assert section_for_url("https://cuet.ac.bd/news/146") == "news-events"


# -- citations that resolve -------------------------------------------------

HOME = {"data": {
    "alumni_news": [{"id": 146, "title": "A reunion", "date": "2026-01-01",
                     "description": "<p>Body.</p>"}],
    "alumni_notices": [{"id": 332, "title": "A notice",
                        "publish_date": "2026-01-01", "pdf": None,
                        "external_link": None}],
    "alumni_events": [], "alumni_photo_galleries": [], "alumni_siders": [],
}}


def test_a_notice_cites_the_listing_because_no_per_notice_page_exists():
    """/notices/<id> returns 404 on this host. A citation a reader cannot open
    is worse than a coarser one they can."""
    result = _build(alumni.build_alumni_news,
                    _dump(**{"/alumni-home-data": HOME}))
    notice = [d for d in result.documents if d.group == "notices"][0]
    assert notice.url == f"{SITE}/notices"
    assert "/notices/332" not in notice.url


def test_notices_sharing_one_url_still_get_distinct_ids():
    """Because they all cite the listing, the id has to come from the key."""
    two = {"data": dict(HOME["data"],
                        alumni_notices=[
                            {"id": 332, "title": "One", "publish_date": "x"},
                            {"id": 333, "title": "Two", "publish_date": "y"}])}
    result = _build(alumni.build_alumni_news,
                    _dump(**{"/alumni-home-data": two}))
    notices = [d for d in result.documents if d.group == "notices"]
    assert len({d.key for d in notices}) == 2


def test_a_news_item_cites_its_own_page_which_does_exist():
    result = _build(alumni.build_alumni_news,
                    _dump(**{"/alumni-home-data": HOME}))
    news = [d for d in result.documents if d.group == "news"][0]
    assert news.url == f"{SITE}/news/146"


def test_responsibilities_cite_the_homepage_they_are_rendered_on():
    rows = {"data": [{"id": 1, "slug": "scholarship", "title": "Scholarship",
                      "description": "<p>Give one.</p>"}]}
    result = _build(alumni.build_alumni_responsibilities,
                    _dump(**{"/alumni-responsibilities": rows}))
    doc = result.documents[0]
    assert doc.url == f"{SITE}/"
    assert doc.key.endswith("?_responsibility=scholarship")


def test_settings_keys_only_cite_routes_that_exist():
    """/privacy-policy was the obvious guess from the key name and it is a 404.
    Every route this module cites must be one that was actually requested."""
    assert set(alumni.SETTINGS_PAGES.values()) <= {"/", "/about"}


def test_two_settings_keys_on_one_route_stay_two_documents():
    settings = {"data": {
        "about_us": {"key": "about_us", "value": "<p>About.</p>"},
        "president_message": {"key": "president_message", "value": "<p>Hello.</p>"},
    }}
    result = _build(alumni.build_alumni_pages,
                    _dump(**{"/alumni-settings": settings}))
    assert len(result.documents) == 2
    assert len({d.key for d in result.documents}) == 2
    assert {d.url for d in result.documents} == {f"{SITE}/about"}


# -- degrading without the endpoint ----------------------------------------

def test_a_failed_endpoint_warns_instead_of_raising():
    """A dead vendor host must not take down the portions that do not use it."""
    dump = {"_alumni": {"/alumni-settings": {"status": None,
                                                    "error": "Timeout"}}}
    result = _build(alumni.build_alumni_pages, dump)
    assert result.documents == []
    assert "alumni_settings_missing" in result.warnings


def test_an_empty_cms_value_produces_nothing_rather_than_an_empty_document():
    settings = {"data": {"president_message": {"key": "president_message",
                                               "value": None}}}
    result = _build(alumni.build_alumni_pages,
                    _dump(**{"/alumni-settings": settings}))
    assert result.documents == []
