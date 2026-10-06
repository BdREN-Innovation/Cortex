"""Link harvesting, and the entity bug that made the gap diff unusable.

An href in HTML is entity-encoded. The faculty slug that reads
`architecture-&-planning` in a URL bar is written `architecture-&amp;-planning`
in the markup, and CUET has three faculties plus one section with a literal
ampersand (spec §4.2). Recording the encoded form produces a URL that does not
exist, and worse, it silently breaks the Appendix B gap diff: the discovered
form and the stored form become different strings, so a page that IS captured
is reported as missing.
"""

from __future__ import annotations

from engine.crawler.cuet.builders.base import Stage2Result, harvest

SITE = "https://cuet.ac.bd"


def _pages(markup: str, base: str = SITE) -> set[str]:
    result = Stage2Result()
    harvest(markup, base, result, linked_from=f"{base}/from")
    return result.found_pages


def test_an_encoded_ampersand_is_decoded():
    """The regression. 903 of 1,127 harvested URLs carried a raw &amp;."""
    found = _pages('<a href="/faculty/architecture-&amp;-planning">Faculty</a>')
    assert found == {f"{SITE}/faculty/architecture-&-planning"}


def test_all_three_ampersand_faculties_decode():
    markup = "".join(
        f'<a href="/faculty/{slug}">x</a>' for slug in (
            "architecture-&amp;-planning",
            "electrical-&amp;-computer-engineering",
            "science-&amp;-technology",
        )
    )
    assert _pages(markup) == {
        f"{SITE}/faculty/architecture-&-planning",
        f"{SITE}/faculty/electrical-&-computer-engineering",
        f"{SITE}/faculty/science-&-technology",
    }


def test_a_numeric_entity_decodes_too():
    """The site is not consistent about which form it emits."""
    assert _pages('<a href="/section/l&#38;e">x</a>') == {f"{SITE}/section/l&e"}


def test_the_decoded_url_matches_what_the_scraper_stores():
    """The point of the fix.

    `page_id` and `canonical` operate on the decoded form, so an encoded href
    and the document built from the API must agree, or the gap diff reports a
    captured page as missing.
    """
    from engine.crawler.cuet.paths import canonical, page_id
    stored = f"{SITE}/faculty/science-&-technology"
    discovered = next(iter(_pages('<a href="/faculty/science-&amp;-technology">x</a>')))
    assert discovered == canonical(stored)
    assert page_id(discovered) == page_id(stored)


def test_a_query_string_ampersand_is_not_mangled():
    """`&amp;` between query parameters decodes to a real separator, which is
    what the server expects. Leaving it encoded sends a single bogus parameter."""
    found = _pages('<a href="/search?a=1&amp;b=2">x</a>')
    assert found == {f"{SITE}/search?a=1&b=2"}


def test_decoding_happens_before_the_scheme_filter():
    """`&#106;avascript:` decodes to `javascript:`. Filtering first would let
    it through as an ordinary relative link."""
    assert _pages('<a href="&#106;avascript:alert(1)">x</a>') == set()


def test_decoding_happens_before_the_image_filter():
    """Spec §4.6 is a firm requirement, so an encoded image URL must not slip
    past it either."""
    assert _pages('<a href="/assets/images/a&amp;b.jpg">x</a>') == set()


def test_an_encoded_file_url_is_recorded_as_a_file():
    result = Stage2Result()
    harvest('<a href="https://app.cuet.ac.bd/storage/x&amp;y.pdf">pdf</a>',
            SITE, result, linked_from=f"{SITE}/from")
    assert list(result.found_files) == [
        "https://app.cuet.ac.bd/storage/x&y.pdf"]


def test_ordinary_links_are_unaffected():
    assert _pages('<a href="/department/cse">CSE</a>') == {f"{SITE}/department/cse"}


def test_the_sites_own_broken_hrefs_are_still_dropped():
    """Spec §4.8: every dropdown toggle carries href="#", plus mailto:undefined
    and tel:undefined."""
    markup = ('<a href="#">t</a><a href="mailto:undefined">m</a>'
              '<a href="tel:undefined">p</a><a href="javascript:void(0)">j</a>')
    assert _pages(markup) == set()
