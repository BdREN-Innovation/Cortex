"""The frontier remembers every URL it turns away, and why."""

from __future__ import annotations

from engine.crawler import skips
from engine.crawler.frontier import Frontier, ScopeRules

HOME = "https://site.test/"


def _frontier() -> Frontier:
    rules = ScopeRules(
        allowed_domains=["site.test"], exclude_patterns=[r"/login"], max_depth=1
    )
    return Frontier([HOME], rules)


def test_links_turned_away_are_recorded_with_reason_and_parent():
    frontier = _frontier()
    frontier.add_links(
        HOME, ["/about", "https://other.test/page", "/login", "ftp://site.test/file"], 0
    )

    skipped = {skip.url: skip for skip in frontier.skipped()}

    assert skipped["https://other.test/page"].reason == skips.OFF_SCOPE
    assert skipped["https://site.test/login"].reason == skips.OFF_SCOPE
    assert skipped["ftp://site.test/file"].reason == skips.INVALID_URL
    assert all(skip.parent_url == HOME for skip in skipped.values())
    assert "https://site.test/about" not in skipped
    assert frontier.parent_of("https://site.test/about") == HOME


def test_a_link_too_deep_on_one_page_is_forgiven_when_found_shallower():
    frontier = _frontier()
    frontier.add_links("https://site.test/about", ["/deep"], 1)
    assert [skip.reason for skip in frontier.skipped()] == [skips.MAX_DEPTH]

    frontier.add_links(HOME, ["/deep"], 0)

    assert frontier.skipped() == []


def test_drain_records_what_was_still_queued():
    frontier = _frontier()
    frontier.add_links(HOME, ["/about"], 0)

    left = frontier.drain(skips.MAX_PAGES)

    assert [(skip.url, skip.reason, skip.parent_url) for skip in left] == [
        (HOME, skips.MAX_PAGES, ""),
        ("https://site.test/about", skips.MAX_PAGES, HOME),
    ]
    assert not frontier
