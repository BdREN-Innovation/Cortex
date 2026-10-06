"""Portion `academic`: departments, faculties, institutes, centres, curricula.

On the website: the Academic menu — /departments, /faculty, /institutes,
/centers and every /department/<slug> detail page — plus the curriculum lists
under /academic-information.

Owner: see `portions.py`.
"""

from __future__ import annotations

import logging

from .. import config
from .base import (Document, Stage2Result, _clean_html, _headline_body,
                   _rows, harvest)

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
            extra={"origin": f"API {config.ENTITY_DETAIL}",
                   "slug": slug, "entity_type": etype,
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
            extra={"origin": "API /academic-curriculums",
                   "curriculum_type": curriculum_type,
                   "curriculum_ids": [r.get("id") for r in group]},
        ))




# --------------------------------------------------------------------------
# Faculty members
# --------------------------------------------------------------------------

def _public_person(row: dict, detail: dict) -> dict:
    """Merge a roster row with its detail, dropping what the site never shows.

    Two separate field lists because the API nests them differently, and both
    are applied here rather than at the point of writing: a person object that
    has never held a home address cannot leak one later by accident.
    """
    person = {k: v for k, v in row.items()
              if k not in config.FACULTY_PRIVATE_FIELDS}
    if not isinstance(detail, dict) or "error" in detail:
        return person
    data = detail.get("data") if isinstance(detail.get("data"), dict) else detail
    if not isinstance(data, dict):
        return person
    for key, value in data.items():
        if key in config.FACULTY_PRIVATE_FIELDS:
            continue
        if key == "profile" and isinstance(value, dict):
            value = {k: v for k, v in value.items()
                     if k not in config.FACULTY_PRIVATE_PROFILE_FIELDS}
        person[key] = value
    return person


def _person_sections(person: dict) -> str:
    """The professional record, as HTML.

    Rendered here rather than left as JSON because the corpus stores documents,
    and a retrieval system searching a person's publications should find prose,
    not a serialised list.
    """
    parts: list[str] = []
    profile = person.get("profile") if isinstance(person.get("profile"), dict) else {}
    # `education_intro` is prose, not rows, and for many people it is the ONLY
    # place their degrees appear - `educations` comes back empty while this
    # field holds the whole list. It gets a heading so the section is findable,
    # since without one a search for a person's education matches nothing even
    # though the text is right there.
    intros = (("intro", None), ("education_intro", "Education"),
              ("other_descriptions", "Other"))
    for key, heading in intros:
        text = profile.get(key)
        if isinstance(text, str) and text.strip():
            parts.append(f"<h2>{heading}</h2>{text}" if heading else text)

    listings = (("educations", "Education (listed)"), ("experiences", "Experience"),
                ("researches", "Research"), ("publications", "Publications"),
                ("courses", "Courses"), ("supervisions", "Supervision"),
                ("achievements_awards", "Achievements and awards"))
    for key, heading in listings:
        rows = person.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            # Field names vary per list, so take whatever reads as a label and
            # join the rest of the short scalars behind it.
            # Only the key actually USED as the label is excluded from the
            # rest. Excluding every candidate drops real content: an education
            # row is {degree, institute}, so taking `degree` as the label and
            # then skipping `institute` too loses the university's name.
            label_key = next(
                (k for k in ("title", "name", "degree", "designation", "institute")
                 if row.get(k)), None)
            label = row.get(label_key) if label_key else ""
            rest = [str(v) for k, v in row.items()
                    if k not in ("id", "admin_id", label_key)
                    and isinstance(v, (str, int)) and str(v).strip()]
            line = " - ".join(x for x in [str(label).strip(), ", ".join(rest)] if x)
            if line:
                items.append(f"<li>{line}</li>")
        if items:
            parts.append(f"<h2>{heading}</h2><ul>{''.join(items)}</ul>")
    return "\n".join(parts)


def build_faculty_members(dump: dict, result: Stage2Result) -> None:
    """One document per faculty member. Spec Appendix B, closed 2026-09-09.

    Until now the corpus held 30 people: the heads, whose profile URLs the
    department payload names. The other 344 were not missing because anyone
    decided against them - the department faculty-members pages render an empty
    grid, so rendering them found nothing, and the endpoint that fills that grid
    was not in the audited set. Coverage checks that only ever look at pages
    cannot find a hole like that.
    """
    faculty = dump.get("_faculty")
    if not isinstance(faculty, dict) or "error" in faculty:
        log.warning("faculty data missing from the dump; no faculty documents")
        result.warnings.append("faculty_missing")
        return

    rows = faculty.get("list") or []
    details = faculty.get("details") or {}
    built = 0
    for row in rows:
        slug = row.get("slug")
        if not slug:
            continue
        person = _public_person(row, details.get(slug) or {})
        url = (f"{config.SITE}"
               f"{config.HEAD_PROFILE_TEMPLATE.format(slug=slug)}")
        name = person.get("name") or slug
        department = person.get("administrative_department_title") or ""
        positions = person.get("admin_positions")
        title = ""
        if isinstance(positions, list) and positions:
            first = positions[0]
            if isinstance(first, dict):
                title = first.get("title") or first.get("designation") or ""

        facts = [("Designation", title), ("Department", department),
                 ("Email", person.get("email")), ("Phone", person.get("phone")),
                 ("Room", person.get("room_no")),
                 ("Status", person.get("employee_status"))]
        body = _headline_body(name, facts)
        sections = _person_sections(person)
        if sections:
            html, escaped = _clean_html(sections, result, f"faculty.{slug}")
            body = f"{body}\n{html}"
        else:
            escaped = False

        doc = Document(
            url=url, title=name, html=body,
            section="academic", group="profiles",
            section_path=["Academic", "Faculty", department or "CUET", name],
            extra={"origin": f"API {config.FACULTY_DETAIL}",
                   "slug": slug, "department": department,
                   "employee_status": person.get("employee_status"),
                   "admin_type": person.get("admin_type"),
                   "private_fields_dropped":
                       list(config.FACULTY_PRIVATE_FIELDS)
                       + [f"profile.{f}" for f in
                          config.FACULTY_PRIVATE_PROFILE_FIELDS]},
            double_escaped=escaped,
        )
        doc.files = harvest(body, config.SITE, result, linked_from=url,
                            meta={"document_type": "faculty_profile"})
        result.documents.append(doc)
        built += 1
    log.info("faculty: %d documents from %d roster rows", built, len(rows))
