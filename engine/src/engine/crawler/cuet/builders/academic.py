"""Portion `academic`: departments, faculties, institutes, centres, curricula.

On the website: the Academic menu — /departments, /faculty, /institutes,
/centers and every /department/<slug> detail page — plus the curriculum lists
under /academic-information.

Owner: see `portions.py`.
"""

from __future__ import annotations

import logging

from .. import config
from .base import Document, Stage2Result, _clean_html, _rows, harvest

log = logging.getLogger(__name__)


def build_entities(dump: dict, result: Stage2Result) -> None:
    """Departments, institutes, centres and faculties. Spec §3.5.

    The body is assembled from the entity's HTML fields in a fixed order, each
    under a heading naming its field. Not concatenated bare: the field name is
    the only thing telling a reader whether they are looking at the department's
    self-description or its head's welcome message, and that distinction has to
    survive into chunking and citation.
    """
    fields = [
        ("about", "About"),
        ("vision", "Vision"),
        ("mission", "Mission"),
        ("message_from_head", "Message from the Head"),
        ("laboratories_intro", "Laboratories"),
    ]
    route = {"academic": "/department/{}", "institute": "/institutes/{}",
             "center": "/centers/{}", "faculty": "/faculty/{}"}

    for slug, detail in (dump.get("_entity_details") or {}).items():
        if not isinstance(detail, dict) or "error" in detail:
            continue
        entity = detail.get("data") if isinstance(detail.get("data"), dict) else detail
        etype = entity.get("type")
        template = route.get(etype)
        if not template:
            continue

        url = f"{config.SITE}{template.format(slug)}"
        title = entity.get("title") or slug

        parts: list[str] = []
        for key, heading in fields:
            value = entity.get(key)
            if isinstance(value, str) and value.strip():
                html, escaped = _clean_html(value, result, f"{slug}.{key}")
                parts.append(f"<h2>{heading}</h2>\n{html}")
                if escaped:
                    result.warnings.append(f"double_escaped:{slug}.{key}")

        head = entity.get("department_head")
        if isinstance(head, dict) and head.get("name"):
            parts.append(
                f"<h2>Head</h2><p>{head.get('name')}"
                + (f" &mdash; {head.get('email')}" if head.get("email") else "")
                + "</p>"
            )

        # `contacts` IS the /department/<slug>/contact page. Spec §3.5.
        contacts = entity.get("contacts")
        if isinstance(contacts, list) and contacts:
            rows = "".join(
                f"<tr><td>{c.get('purpose') or ''}</td><td>{c.get('email') or ''}</td>"
                f"<td>{c.get('phone') or ''}</td></tr>"
                for c in contacts if isinstance(c, dict)
            )
            parts.append(
                "<h2>Contact</h2><table><tr><th>Purpose</th><th>Email</th>"
                f"<th>Phone</th></tr>{rows}</table>"
            )

        if not parts:
            log.info("entity %s has no body fields; skipping", slug)
            continue

        # academicFaculty.title is the breadcrumb level, straight from the API.
        # No join against /administrative-academic-faculties needed. Spec §3.5.
        faculty = entity.get("academicFaculty")
        crumb = ["Academic"]
        crumb.append({"academic": "Departments", "institute": "Institutes",
                      "center": "Centers", "faculty": "Faculties"}[etype])
        if isinstance(faculty, dict) and faculty.get("title"):
            crumb.append(faculty["title"])
        crumb.append(title)

        html = "\n".join(parts)
        doc = Document(
            url=url, title=title, html=html, section="academic",
            group={"academic": "departments", "institute": "institutes",
                   "center": "centers", "faculty": "faculty"}[etype],
            section_path=crumb,
            extra={"slug": slug, "entity_type": etype,
                   "short_name": entity.get("short_name"),
                   "email": entity.get("email"), "phone": entity.get("phone")},
        )
        doc.files = harvest(html, config.SITE, result, linked_from=url,
                            meta={"document_type": "department"})
        result.documents.append(doc)



def build_curricula(dump: dict, result: Stage2Result) -> None:
    """31 curricula, grouped by type into index documents.

    Same reasoning as `build_notices`: a curriculum record is a title and a link
    to a PDF, with `short_description` usually holding just the anchor. One
    document each would be 31 one-line texts. There is also no per-curriculum
    route on the site, so a per-item document would have to cite a URL that does
    not exist.
    """
    rows = _rows(dump.get("/academic-curriculums"))
    if not rows:
        return

    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(row.get("type") or "other", []).append(row)

    for curriculum_type, group in by_type.items():
        label = curriculum_type.replace("_", " ").title()
        url = f"{config.SITE}/academic-information"
        body = [f"<h1>{label} curricula</h1>",
                f"<p>{len(group)} {label.lower()} curriculum documents "
                f"published by CUET.</p>"]
        for row in group:
            title = row.get("title") or f"Curriculum {row.get('id')}"
            html, escaped = _clean_html(row.get("short_description") or "",
                                        result, f"curriculum.{row.get('id')}")
            body.append(f"<h2>{title}</h2>")
            if html.strip():
                body.append(html)
            # The PDF links live inside short_description as anchors.
            harvest(html, config.SITE, result,
                    linked_from=url,
                    meta={"document_type": "curriculum", "title": title,
                          "category": label})

        result.documents.append(Document(
            url=url, key=f"{url}?_curricula={curriculum_type}",
            title=f"{label} curricula", html="\n".join(body),
            section="academic", group="information",
            section_path=["Academic", "Curricula", label],
            extra={"curriculum_type": curriculum_type,
                   "curriculum_ids": [r.get("id") for r in group]},
        ))

