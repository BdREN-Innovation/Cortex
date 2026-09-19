"""A corpus that is two pages short must say so itself.

The admission host linked from the Admission menu has no DNS record. Nothing
can be done about that, which is exactly why it needs writing down: a corpus
missing two pages for a good reason looks identical to one missing two pages
because somebody forgot.
"""

from __future__ import annotations

import json

from engine.crawler.cuet import config
from engine.crawler.cuet.merge import write_known_gaps

PLANNED = {
    "https://cuet.ac.bd/departments": "listing page",
    "https://admissioncuet.ac.bd": "separate host",
    "https://admissioncuet.ac.bd/about-us": "separate host",
}


def _gaps(tmp_path, captured):
    write_known_gaps(tmp_path, PLANNED, captured)
    return json.loads((tmp_path / "_meta" / "known_gaps.json")
                      .read_text(encoding="utf-8"))


def test_an_unreachable_host_is_recorded_with_its_reason(tmp_path):
    data = _gaps(tmp_path, {"https://cuet.ac.bd/departments"})
    assert data["count"] == 2
    for gap in data["gaps"]:
        assert gap["state"] == "unreachable"
        assert "no DNS record" in gap["reason"]


def test_an_unreachable_gap_is_marked_not_actionable(tmp_path):
    """So nobody re-runs the crawler hoping it will fix itself."""
    data = _gaps(tmp_path, {"https://cuet.ac.bd/departments"})
    assert all(gap["actionable"] is False for gap in data["gaps"])


def test_a_gap_on_a_live_host_is_actionable(tmp_path):
    """The distinction is the whole point of the file: one of these is worth
    somebody's afternoon and the other never will be."""
    data = _gaps(tmp_path, {"https://admissioncuet.ac.bd",
                            "https://admissioncuet.ac.bd/about-us"})
    assert data["count"] == 1
    gap = data["gaps"][0]
    assert gap["url"] == "https://cuet.ac.bd/departments"
    assert gap["actionable"] is True
    assert gap["state"] == "not captured"


def test_a_complete_run_still_writes_the_file(tmp_path):
    """An empty gaps file is a statement. A missing one is ambiguous."""
    data = _gaps(tmp_path, set(PLANNED))
    assert data["count"] == 0
    assert data["gaps"] == []


def test_the_reason_survives_from_config(tmp_path):
    """The text a reader sees comes from UNRESOLVABLE_HOSTS, so the evidence
    lives in one place rather than being retyped here."""
    data = _gaps(tmp_path, set())
    reasons = {g["reason"] for g in data["gaps"] if g["state"] == "unreachable"}
    assert reasons == {config.UNRESOLVABLE_HOSTS["admissioncuet.ac.bd"]}


def test_every_unresolvable_host_carries_an_explanation():
    """The container changed from a set of names to a mapping precisely so that
    a host cannot be listed without saying why."""
    assert isinstance(config.UNRESOLVABLE_HOSTS, dict)
    for host, reason in config.UNRESOLVABLE_HOSTS.items():
        assert reason.strip(), host
