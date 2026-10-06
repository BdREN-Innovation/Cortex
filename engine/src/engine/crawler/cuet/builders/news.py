"""Portion `news-events`: news items and events.

On the website: the News & Events menu — the /news-events listing, each
/news/<id> article, and each /event-details/<id> page.

Owner: see `portions.py`.
"""

from __future__ import annotations

import logging

from .. import config
from ..paths import canonical
from .base import Document, Stage2Result, _clean_html, _headline_body, _rows, harvest

log = logging.getLogger(__name__)


def build_news(dump: dict, result: Stage2Result) -> None:
    """157 news items with full HTML bodies. Spec §4.9."""
    for row in _rows(dump.get("/news")):
        nid = row.get("id")
        if nid is None:
            continue
        url = f"{config.SITE}/news/{nid}"
        title = row.get("title") or f"News {nid}"
        html, escaped = _clean_html(row.get("description") or "", result, f"news.{nid}")
        if not html.strip():
            html = _headline_body(title, [("Published", row.get("date"))])
            result.warnings.append(f"headline_only:news.{nid}")
        doc = Document(
            url=url, title=title, html=html,
            section="news-events", group="news",
            section_path=["News & Events", "News", title],
            extra={"origin": "API /news",
                   "news_id": nid, "date": row.get("date"),
                   "headline_only": not (row.get("description") or "").strip()},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.SITE, result, linked_from=url,
                            meta={"document_type": "news",
                                  "published_date": row.get("date")})
        result.documents.append(doc)


def build_events(dump: dict, result: Stage2Result) -> None:
    """Events. Every one carries a conference URL, which matters more than the body.

    Two of the three events have little or no `description`, but all three name a
    conference and link its site — `icace.cuet.ac.bd`, `ecce2027.cuet.ac.bd`,
    `iciurp.cuet.ac.bd`. Those subdomains appear nowhere else in the capture, so
    dropping a short event record loses the only pointer to them.
    """
    for row in _rows(dump.get("/events")):
        eid = row.get("id")
        if eid is None:
            continue
        url = f"{config.SITE}/event-details/{eid}"
        title = row.get("title") or f"Event {eid}"
        html, escaped = _clean_html(row.get("description") or "", result, f"event.{eid}")
        facts = [("From", row.get("from")), ("To", row.get("to")),
                 ("Location", row.get("location")), ("Website", row.get("link"))]
        if not html.strip():
            html = _headline_body(title, facts)
            result.warnings.append(f"headline_only:event.{eid}")
        else:
            # Even with a body, the schedule and link live in sibling fields and
            # would otherwise never reach the text.
            html = html + "\n" + _headline_body("Details", facts).split("\n", 1)[1]
        doc = Document(
            url=url, title=title, html=html,
            section="news-events", group="event-details",
            section_path=["News & Events", "Events", title],
            extra={"origin": "API /events",
                   "event_id": eid, "from": row.get("from"), "to": row.get("to"),
                   "location": row.get("location"), "link": row.get("link"),
                   "headline_only": not (row.get("description") or "").strip()},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.SITE, result, linked_from=url,
                            meta={"document_type": "event"})
        # The conference site is a link worth recording even though it is
        # off-host and will not be followed.
        if row.get("link"):
            result.found_pages.add(canonical(row["link"]))
        result.documents.append(doc)

