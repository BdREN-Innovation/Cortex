"""Portion `general`: the CMS page bodies and the student organisations.

On the website these are the About menu, the campus-life and prospective-student
pages, and the Student Organizations listing. They share a module because both
are small, flat sources with no per-item route worth splitting further.

Owner: see `portions.py`.
"""

from __future__ import annotations

import logging

from .. import config
from .base import (Document, Stage2Result, _body, _clean_html, _rows,
                   _setting_value, harvest)

log = logging.getLogger(__name__)


def build_cms(dump: dict, result: Stage2Result) -> None:
    """The eight page bodies in /general-settings. Spec §3.3."""
    body = _body(dump.get("/general-settings"))
    settings = body.get("data") if isinstance(body, dict) and isinstance(
        body.get("data"), dict) else body
    if not isinstance(settings, dict):
        settings = {}

    for key, path in config.CMS_CONTENT_KEYS.items():
        raw = _setting_value(settings, key)
        if not raw.strip():
            log.warning("CMS key %s missing or empty", key)
            result.warnings.append(f"cms_missing:{key}")
            continue
        html, escaped = _clean_html(raw, result, key)
        url = f"{config.SITE}{path}"
        doc = Document(
            url=url, title=path.strip("/").replace("/", " / "), html=html,
            section="_cms", group="", section_path=["CMS", key],
            extra={"cms_key": key, "renders_page": path},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.SITE, result, linked_from=url,
                            meta={"document_type": "cms"})
        result.documents.append(doc)



def build_student_organizations(dump: dict, result: Stage2Result) -> None:
    for row in _rows(dump.get("/student-organizations")):
        slug = row.get("slug")
        if not slug:
            continue
        url = f"{config.SITE}/student/organization/{slug}"
        html, escaped = _clean_html(row.get("description") or "", result, f"org.{slug}")
        doc = Document(
            url=url, title=row.get("title") or slug, html=html,
            section="home", group="organizations",
            section_path=["Student Organizations", row.get("title") or slug],
            extra={"slug": slug, "org_type": row.get("type")},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.SITE, result, linked_from=url,
                            meta={"document_type": "organization"})
        result.documents.append(doc)

