"""Portion `general`: the administration entities — directorates, offices, sections.

On the website: the Administration menu, the Directorates and the
"Offices & Sections" column in the footer — /directorate/<slug>,
/office/<slug> and /section/<slug>.

Two endpoints, joined on `id`:

* **/footer-data** carries the ROUTES. Its three lists — `directorates`,
  `administrative_offices`, `office_section` — are the only place the site says
  which entities are published under which URL prefix, and with which slug.
* **/administrative-departments** carries the BODIES. 63 entities, of which
  these 21 are a subset; the rest are academic departments and belong to the
  `academic` portion.

Neither endpoint is sufficient alone: the bodies carry no route, and the routes
carry no prose.

Slugs come from /footer-data verbatim, never normalised. `DSW` is uppercase,
`citizen_charter` uses an underscore where the other APA slugs use a hyphen, and
the API spells the DRE slug `research-extension` while the site's own nav links
`research-extenstion`. All three API forms were checked against the live site on
2026-09-09 and resolve; the nav typo is the site's broken link, not ours.
Constructing a "corrected" slug would emit a citation that 404s for the reader —
the failure mode `notices.py` documents at length.

Owner: see the portion registry.
"""

from __future__ import annotations

import logging

from .. import config
from .base import Document, Stage2Result, _body, _clean_html, _rows, harvest

log = logging.getLogger(__name__)


# (key in /footer-data, URL prefix on cuet.ac.bd, output group, breadcrumb root)
#
# The URL prefix is NOT derivable from the entity's `type` field: DSW and IQAC
# are type "directorate" while ITBI and BRTC are type "cell", and all four are
# published under /directorate/. The list a slug appears in is what decides its
# route, which is why this table is keyed on the /footer-data key.
_ENTITY_GROUPS = (
    ("directorates", "/directorate", "directorates", "Directorates"),
    ("administrative_offices", "/office", "offices", "Administration"),
    ("office_section", "/section", "sections", "Offices & Sections"),
)

# Rendered in this order. `message_from_head` is first because it is the only
# body field 20 of the 21 entities actually populate — for most of them it IS
# the page.
_BODY_FIELDS = (
    ("message_from_head", "Message from the Head"),
    ("about", "About"),
    ("vision", "Vision"),
    ("mission", "Mission"),
    ("notice_intro", "Notices"),
    ("publication_intro", "Publications"),
)

# Worth keeping even though it is not prose: "what is the Registrar's phone
# number" is exactly the kind of question this corpus should answer, and the
# contact directory is otherwise only on /directories.
_CONTACT_FIELDS = (
    ("email", "Email"),
    ("phone", "Phone"),
    ("address", "Address"),
    ("departmental_code", "Code"),
)


def build_administration(dump: dict, result: Stage2Result) -> None:
    """21 entities: 6 directorates, 3 offices, 6 sections. Verified 2026-09-09.

    One document per entity, unlike `build_notices` which indexes. The choice
    differs because the content does: a notice is a title and a PDF link, so 265
    of them make 265 near-identical vectors. An entity here carries real prose —
    a head's message, an about section, contact details — under a URL a reader
    can open. That is a document.

    An entity with no body still gets one. `transport-section` returns every
    prose field null, and dropping it would mean the corpus cannot answer that
    CUET has a transport section at all. A title and a phone number are content;
    thin-page filtering is Team B's `--min-text-chars` decision, taken later and
    reversibly. Spec §4.4.
    """
    footer = _body(dump.get("/footer-data"))
    data = footer.get("data") if isinstance(footer, dict) else None
    if not isinstance(data, dict):
        log.warning("/footer-data has no data object; no administration documents")
        result.warnings.append("footer_data_missing")
        return

    # The bodies, indexed by the id /footer-data joins on.
    entities = {
        row.get("id"): row
        for row in _rows(dump.get("/administrative-departments"))
        if row.get("id") is not None
    }
    if not entities:
        log.warning("/administrative-departments empty; entities will have titles only")
        result.warnings.append("administrative_departments_empty")

    written = thin = 0

    for footer_key, prefix, group, crumb in _ENTITY_GROUPS:
        listed = data.get(footer_key)
        if not isinstance(listed, list) or not listed:
            log.warning("/footer-data.%s missing or empty", footer_key)
            result.warnings.append(f"footer_group_missing:{footer_key}")
            continue

        for entry in listed:
            if not isinstance(entry, dict):
                continue
            slug = entry.get("slug")
            if not slug:
                # No slug means no route, and a document with no citable URL is
                # worse than no document.
                log.warning("%s entry %r has no slug; skipped", footer_key, entry.get("title"))
                result.warnings.append(f"entity_no_slug:{footer_key}:{entry.get('id')}")
                continue

            row = entities.get(entry.get("id")) or {}
            title = row.get("title") or entry.get("title") or slug
            url = f"{config.SITE}{prefix}/{slug}"

            parts = [f"<h1>{title}</h1>"]

            bangla = row.get("bn_title") or entry.get("bn_title")
            if bangla:
                # Kept as its own line rather than folded into the heading: it is
                # the entity's official Bangla name, and a bilingual corpus should
                # be able to match a question asked in either language.
                parts.append(f"<p>{bangla}</p>")

            short = entry.get("short_name") or row.get("short_name")
            if short and short.lower() != str(slug).lower():
                parts.append(f"<p>Also known as: {short}</p>")

            double_escaped = False
            has_prose = False
            for field, label in _BODY_FIELDS:
                raw = row.get(field)
                if not isinstance(raw, str) or not raw.strip():
                    continue
                html, escaped = _clean_html(raw, result, f"{group}.{slug}.{field}")
                double_escaped = double_escaped or escaped
                parts.append(f"<h2>{label}</h2>")
                parts.append(html)
                has_prose = True

            contact = [
                f"<p>{label}: {row.get(field)}</p>"
                for field, label in _CONTACT_FIELDS
                if row.get(field)
            ]
            if contact:
                parts.append("<h2>Contact</h2>")
                parts.extend(contact)

            if not has_prose:
                thin += 1
                log.info("%s: no prose fields, capturing title and contact only", slug)

            html = "\n".join(parts)
            doc = Document(
                url=url,
                title=title,
                html=html,
                section="administration",
                group=group,
                section_path=[crumb, title],
                extra={
                    "origin": "API /administrative-departments + /footer-data",
                    "slug": slug,
                    "entity_id": entry.get("id"),
                    "entity_type": entry.get("type") or "office",
                    "short_name": short,
                    "has_prose": has_prose,
                    "footer_group": footer_key,
                },
                double_escaped=double_escaped,
            )
            # Every body block goes through harvest: a head's message routinely
            # links an office order PDF, and an unharvested link is a file that
            # never gets downloaded and never reaches the corpus.
            doc.files = harvest(
                html, config.SITE, result,
                linked_from=url,
                meta={"document_type": "administration", "entity_slug": slug},
            )
            result.documents.append(doc)
            written += 1

    log.info("administration: %d documents (%d with no prose body)", written, thin)