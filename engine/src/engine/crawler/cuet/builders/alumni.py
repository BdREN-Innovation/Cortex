"""Portion `alumni`: the alumni site at alumni.cuet.ac.bd.

On the website this is the ALUMNI link in the top bar, which leaves cuet.ac.bd
for a second Next.js frontend on its own host. Spec §13 Q9 left that host out of
scope pending a decision; the decision was taken on 2026-09-09 and this module
is it.

**Why fetching it is allowed.** alumni.cuet.ac.bd/robots.txt returns 404, the
same as the main site's, and its pages carry no robots meta tag. Nothing on the
host asks crawlers to stay away, and the same 1.5-second per-host delay and
contact-carrying User-Agent apply here as everywhere else.

**Why only seven endpoints.** The alumni frontend talks to a vendor backend that
also serves cuet.ac.bd. Its `/notices`, `/news` and `/download-types` are the
university's own rows arriving by a second road: 102 of the 114 news items it
returns were already in the corpus from api.cuet.ac.bd. Capturing those again
would put one notice under two citable URLs, which is the same mistake
`KNOWN_NOT_PLANNED` exists to prevent for /centers/ and /institutes/. What this
module captures is what only the alumni site has, and the alumni-scoped slices
of news and notices come from `/alumni-home-data`, which is the endpoint the
site itself renders.

Owner: see `builders/__init__.py`.
"""

from __future__ import annotations

import logging

from .. import config
from .base import (Document, Stage2Result, _body, _clean_html, _headline_body,
                   harvest)

log = logging.getLogger(__name__)

# The /alumni-settings keys that hold a page body, and the alumni-site route
# each one renders. Keys carrying a phone number, a social link or a count are
# deliberately absent: they are fields, not documents.
# VERIFIED 2026-09-09 by requesting each one: /about and / return 200.
# /privacy-policy, /copyright-policy and /circulation-rules do NOT exist - they
# were the obvious guess from the setting name and all three return 404. That
# text is footer content with no page of its own, so it cites the homepage,
# which is where a reader can actually see it.
SETTINGS_PAGES = {
    "about_us": "/about",
    "home_about_us": "/",
    "president_message": "/about",
    "privacy_policy": "/",
    "copyright_policy": "/",
    "circulation_rules_english": "/",
    "circulation_rules_bangla": "/",
}


def _alumni_block(dump: dict, path: str):
    """One alumni endpoint's parsed body, or None.

    Reads from the `_alumni` namespace rather than the top level, because the
    two hosts share route names and a flat dictionary would let one silently
    overwrite the other. See `discover._fetch_alumni`.
    """
    block = (dump.get("_alumni") or {}).get(path)
    if not isinstance(block, dict) or "error" in block:
        return None
    return _body(block)


def _alumni_rows(dump: dict, path: str) -> list[dict]:
    body = _alumni_block(dump, path)
    data = body.get("data") if isinstance(body, dict) else body
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _settings(dump: dict) -> dict:
    body = _alumni_block(dump, "/alumni-settings")
    if not isinstance(body, dict):
        return {}
    data = body.get("data")
    return data if isinstance(data, dict) else body


def _value(settings: dict, key: str) -> str:
    """One /alumni-settings value.

    Same `{"id", "key", "value"}` wrapper the university's /general-settings
    uses, which is unsurprising - one vendor built both - so `value` may itself
    be None where the CMS field was never filled in.
    """
    raw = settings.get(key)
    if isinstance(raw, dict):
        raw = raw.get("value")
    return raw if isinstance(raw, str) else ""


def build_alumni_pages(dump: dict, result: Stage2Result) -> None:
    """The alumni CMS bodies from /alumni-settings.

    `president_message` is currently null in the CMS and produces nothing. It
    is still listed in SETTINGS_PAGES rather than dropped, so that the day
    somebody fills it in it is captured without anyone having to notice.
    """
    settings = _settings(dump)
    if not settings:
        log.warning("alumni: /alumni-settings missing; no CMS documents built")
        result.warnings.append("alumni_settings_missing")
        return

    for key, path in SETTINGS_PAGES.items():
        raw = _value(settings, key)
        if not raw.strip():
            log.info("alumni CMS key %s is empty; nothing to build", key)
            continue
        html, escaped = _clean_html(raw, result, f"alumni.{key}")
        url = f"{config.ALUMNI_SITE}{path}"
        doc = Document(
            url=url,
            # Several keys render onto the same route (`about_us` and
            # `president_message` are both /about), so the key goes in the
            # document key. A query parameter, not a fragment: canonical()
            # strips fragments and every part would collapse onto one id.
            key=f"{url}?_key={key}",
            title=key.replace("_", " ").title(),
            html=html, section="alumni", group="pages",
            section_path=["Alumni", key.replace("_", " ").title()],
            extra={"origin": "ALUMNI API /alumni-settings",
                   "cms_key": key, "renders_page": path, "site": "alumni"},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.ALUMNI_SITE, result, linked_from=url,
                            meta={"document_type": "alumni_cms"})
        result.documents.append(doc)


def build_alumni_responsibilities(dump: dict, result: Stage2Result) -> None:
    """The four `alumni-responsibilities` items, each with a real body."""
    for row in _alumni_rows(dump, "/alumni-responsibilities"):
        slug = row.get("slug") or str(row.get("id") or "")
        if not slug:
            continue
        # No per-item route exists: /alumni-responsibilities/<slug> returns 404
        # for all four. They are sections of the homepage, so that is what they
        # cite, with the slug in the key to keep the four documents distinct.
        url = f"{config.ALUMNI_SITE}/"
        raw = row.get("description") or row.get("short_description") or ""
        html, escaped = _clean_html(raw, result, f"alumni.resp.{slug}")
        if not html.strip():
            html = _headline_body(row.get("title") or slug, [])
        doc = Document(
            url=url, key=f"{url}?_responsibility={slug}",
            title=row.get("title") or slug, html=html,
            section="alumni", group="responsibilities",
            section_path=["Alumni", "Responsibilities", row.get("title") or slug],
            extra={"origin": "ALUMNI API /alumni-responsibilities",
                   "slug": slug, "site": "alumni"},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.ALUMNI_SITE, result, linked_from=url,
                            meta={"document_type": "alumni_responsibility"})
        result.documents.append(doc)


def build_alumni_news(dump: dict, result: Stage2Result) -> None:
    """The alumni-scoped news and notices from /alumni-home-data.

    Taken from here rather than from the vendor's /news, which returns the
    university's whole news list. These are the items the alumni site itself
    puts on its front page, and they cite alumni.cuet.ac.bd/news/<id>, which is
    where a reader following the citation actually lands.
    """
    body = _alumni_block(dump, "/alumni-home-data")
    home = body.get("data") if isinstance(body, dict) and isinstance(
        body.get("data"), dict) else body
    if not isinstance(home, dict):
        log.warning("alumni: /alumni-home-data missing; no news or notices built")
        result.warnings.append("alumni_home_data_missing")
        return

    for row in home.get("alumni_news") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        url = f"{config.ALUMNI_SITE}/news/{row['id']}"
        html, escaped = _clean_html(row.get("description") or "",
                                    result, f"alumni.news.{row['id']}")
        if not html.strip():
            html = _headline_body(row.get("title") or "", [("Date", row.get("date"))])
        doc = Document(
            url=url, title=row.get("title") or f"News {row['id']}", html=html,
            section="alumni", group="news",
            section_path=["Alumni", "News", row.get("title") or str(row["id"])],
            extra={"origin": "ALUMNI API /alumni-home-data (alumni_news)",
                   "news_id": row["id"], "date": row.get("date"), "site": "alumni"},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.ALUMNI_SITE, result, linked_from=url,
                            meta={"document_type": "alumni_news"})
        result.documents.append(doc)

    for row in home.get("alumni_notices") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        # /notices/<id> returns 404; only the listing at /notices exists. The
        # notice id goes in the key so each stays a separate document.
        url = f"{config.ALUMNI_SITE}/notices"
        # A notice IS its PDF: the API row carries a title, a date and a link,
        # and no body at all. The PDF is recorded as a file so stage 5 fetches
        # it; the document exists so the notice is citable and searchable.
        html = _headline_body(
            row.get("title") or f"Notice {row['id']}",
            [("Published", row.get("publish_date")),
             ("Document", row.get("pdf")),
             ("Link", row.get("external_link"))],
        )
        doc = Document(
            url=url, key=f"{url}?_notice={row['id']}",
            title=row.get("title") or f"Notice {row['id']}", html=html,
            section="alumni", group="notices",
            section_path=["Alumni", "Notices", row.get("title") or str(row["id"])],
            extra={"origin": "ALUMNI API /alumni-home-data (alumni_notices)",
                   "notice_id": row["id"], "site": "alumni",
                   "publish_date": row.get("publish_date")},
        )
        doc.files = harvest(html, config.ALUMNI_SITE, result, linked_from=url,
                            meta={"document_type": "alumni_notice"})
        result.documents.append(doc)


def build_alumni_directory(dump: dict, result: Stage2Result) -> None:
    """The alumni directory, with the private fields removed.

    Every key in `config.ALUMNI_PRIVATE_FIELDS` is dropped before anything is
    written. The two records served today are the vendor's seed data, so
    nothing real is being protected yet - which is the argument for putting the
    rule in now rather than when the directory fills up and somebody has to
    remember it under time pressure.

    What survives is what a retrieval corpus can actually use: degree, batch,
    department, graduation year and the person's own public LinkedIn URL.
    """
    rows = _alumni_rows(dump, "/alumnis")
    if not rows:
        return
    dropped = 0
    for row in rows:
        person = {k: v for k, v in row.items()
                  if k not in config.ALUMNI_PRIVATE_FIELDS}
        dropped += len(row) - len(person)
        ident = person.get("studentID") or person.get("id")
        if not ident:
            continue
        url = f"{config.ALUMNI_SITE}/alumnis/{ident}"
        name = person.get("full_name") or str(ident)
        html, escaped = _clean_html(person.get("bio") or "",
                                    result, f"alumni.person.{ident}")
        facts = [("Degree", person.get("degree")),
                 ("Department", person.get("administrative_department_title")),
                 ("Batch", person.get("batch")),
                 ("Passing year", person.get("passing_year")),
                 ("Current position", person.get("current_position")),
                 ("Country", person.get("country"))]
        doc = Document(
            url=url, title=name,
            html=_headline_body(name, facts) + ("\n" + html if html.strip() else ""),
            section="alumni", group="directory",
            section_path=["Alumni", "Directory", name],
            extra={"origin": "ALUMNI API /alumnis",
                   "student_id": person.get("studentID"), "site": "alumni",
                   "private_fields_dropped": list(config.ALUMNI_PRIVATE_FIELDS)},
            double_escaped=escaped,
        )
        result.documents.append(doc)
    log.info("alumni directory: %d people, %d private field values dropped",
             len(rows), dropped)
