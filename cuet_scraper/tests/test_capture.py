"""Failed-render and not-found detection. Pure functions, no browser needed.

These guard the smallest stage but the least recoverable failure: stage 4 covers
the pages with no API second source, so a silent empty capture there cannot be
repaired from `_meta/api_dump.json` the way everything else can.
"""

from __future__ import annotations

from cuet_scraper import config
from cuet_scraper.capture import looks_not_found, render_failed


def test_empty_shell_is_a_failed_render():
    """The body /departments returns without JavaScript. Spec §2."""
    html = "<html><body><table><tr><td></td><td></td></tr></table></body></html>"
    failed, reason = render_failed("", html)
    assert failed
    assert reason == "below_threshold"


def _long(text: str) -> str:
    """A body comfortably above the render threshold.

    Sized from the config rather than hardcoded: the threshold moved from 4,500
    to 13,000 once it was calibrated against real headless renders, and these
    tests silently broke. Deriving the length means the next recalibration
    cannot invalidate them.
    """
    repeats = (config.EMPTY_RENDER_THRESHOLD // len(text)) + 2
    return text * repeats


def test_partial_render_is_caught_by_the_table_check_not_the_length_check():
    """The case a length threshold alone misses, and the reason §7.2 needs two
    conditions.

    /academic-information/academic-calendars returns its title, breadcrumb and
    sidebar — comfortably past any threshold set for the fully-empty case —
    while its data grid is the empty skeleton.
    """
    markdown = "Academic Calendars\n\n" + _long("sidebar navigation text ")
    assert len(markdown.strip()) > config.EMPTY_RENDER_THRESHOLD

    html = "<h1>Academic Calendars</h1><table><tbody><tr><td></td></tr></tbody></table>"
    failed, reason = render_failed(markdown, html)
    assert failed
    assert reason == "empty_data_grid"


def test_a_populated_page_passes():
    markdown = _long("Real content. ")
    html = "<table><tr><td>Computer Science &amp; Engineering</td></tr></table>"
    failed, _ = render_failed(markdown, html)
    assert not failed


def test_threshold_rejects_a_chrome_only_render():
    """The failure that actually happened: three listing pages were captured as
    nav+footer only, at 11,879 chars, and the old 4,500 threshold accepted all
    three. They were byte-identical, which is what gave it away.

    The threshold must sit above the chrome baseline.
    """
    chrome_only = "x" * 11_879
    failed, reason = render_failed(chrome_only, "<div>nav and footer</div>")
    assert failed
    assert reason == "below_threshold"


def test_not_found_is_detected_by_content_not_status():
    """A Next.js [slug] route returns HTTP 200 for any slug and renders
    not-found on the client. Twelve URLs were tested; every one returned 200,
    including a known misspelling. Spec §4.5.
    """
    assert looks_not_found("# 404\n\nThis page could not be found.")
    assert looks_not_found("Page Not Found")


def test_not_found_does_not_fire_on_a_real_page_mentioning_404():
    """A page about HTTP status codes is not itself a 404. The marker check is
    deliberately limited to the first 600 characters for this reason."""
    body = ("Computer Science & Engineering. " * 40
            + "Our web course covers error handling and the 404 status code.")
    assert not looks_not_found(body)
