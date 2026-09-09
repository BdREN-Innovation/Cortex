"""Stage 1: fetch every API endpoint and save the raw responses verbatim.

Saves BEFORE parsing. If the parsing logic turns out to be wrong you want the
original bytes on disk, not a second round of requests against someone else's
server. Spec §6.7.

Also builds `_meta/urls.txt` — the residual crawl plan, which after the
2026-09-08 revision holds only what the API cannot produce. Spec §6.9.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import logging
from pathlib import Path

from . import config
from .api import Blocked, Client
from .paths import canonical, encode_slug, is_excluded_url

log = logging.getLogger(__name__)

# Entity types from /administrative-departments that Part 1 captures.
# Spec §3.5. The rest (hall, section, directorate, cell, office) are Part 2's.
ACADEMIC_ENTITY_TYPES = frozenset({"academic", "institute", "center", "faculty"})


def run(client: Client, out: Path | None = None) -> dict:
    """Fetch all endpoints, dump them verbatim, build the residual URL plan."""
    out = out or config.OUT
    meta = out / "_meta"
    meta.mkdir(parents=True, exist_ok=True)

    dump: dict[str, object] = {}
    failures: list[dict] = []

    for endpoint in config.ENDPOINTS:
        url = f"{config.API}{endpoint.path}"
        try:
            response = client.get(url)
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            # Store the decoded text verbatim alongside the parsed value. The
            # parsed value is convenience; the text is the evidence.
            dump[endpoint.path] = {
                "status": response.status,
                "note": endpoint.note,
                "body": json.loads(response.content.decode("utf-8")),
            }
            log.info("discover %-46s %7d bytes", endpoint.path, len(response.content))
        except (Blocked, Exception) as exc:          # noqa: BLE001
            message = f"{type(exc).__name__}: {exc}"
            failures.append({"endpoint": endpoint.path, "error": message})
            dump[endpoint.path] = {"status": None, "error": message}
            if endpoint.required:
                # Everything downstream is built from these two. Continuing
                # would produce a plausible, quietly incomplete run — which is
                # the failure mode this whole project is trying to avoid.
                raise SystemExit(
                    f"Required endpoint {endpoint.path} failed ({message}).\n"
                    f"Nothing downstream can be trusted without it. Stopping."
                ) from exc
            log.warning("discover %s FAILED (%s) - continuing", endpoint.path, message)

    entities = _entities(dump)
    _fetch_entity_details(client, dump, entities)
    _fetch_faculty(client, dump)
    _fetch_alumni(client, dump)

    # When these bytes actually came off CUET's servers. Stage 2 stamps it onto
    # every document as `fetched_at`, because a document built today from a dump
    # taken last week was NOT fetched today, and a citation that says otherwise
    # is wrong about the one thing a reader would check.
    #
    # It also makes rebuilding idempotent: re-running a portion against an
    # unchanged dump rewrites byte-identical files instead of a few hundred
    # timestamp-only diffs.
    dump["_fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    (meta / "api_dump.json").write_text(
        json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    urls = build_url_plan(dump)
    (meta / "urls.txt").write_text(
        "\n".join(f"{u}\t# {why}" for u, why in urls) + "\n", encoding="utf-8"
    )

    log.info("discover: %d endpoints, %d entity details, %d residual URLs planned",
             len(config.ENDPOINTS), len(dump.get("_entity_details", {}) or {}), len(urls))
    return {"dump": dump, "urls": urls, "failures": failures}


def _entities(dump: dict) -> list[dict]:
    """The entity list from /administrative-departments. Spec §3.5."""
    block = dump.get("/administrative-departments", {})
    body = block.get("body") if isinstance(block, dict) else None
    if not isinstance(body, dict):
        return []
    return [e for e in body.get("data", []) if isinstance(e, dict)]


def _fetch_entity_details(client: Client, dump: dict, entities: list[dict]) -> None:
    """Fetch /administrative-departments/{slug} for each in-scope entity.

    This is where department, institute, centre and faculty page bodies come
    from — including `contacts`, which IS the /department/<slug>/contact page,
    and `academicFaculty.title`, which is the section_path breadcrumb. Spec §3.5.
    """
    details: dict[str, object] = {}
    for entity in entities:
        if entity.get("type") not in ACADEMIC_ENTITY_TYPES:
            continue
        slug = entity.get("slug")
        if not slug:
            continue
        # Every slug is encoded, not just the ones known to contain "&".
        # `l&e` was the fourth such slug found and it was not on anyone's list.
        # Spec §4.2.
        url = f"{config.API}{config.ENTITY_DETAIL.format(slug=encode_slug(slug))}"
        try:
            details[slug] = client.get_json(url)
            log.info("entity %-34s ok", slug)
        except Exception as exc:                     # noqa: BLE001
            details[slug] = {"error": f"{type(exc).__name__}: {exc}"}
            log.warning("entity %s FAILED: %s", slug, exc)
    dump["_entity_details"] = details


def _fetch_faculty(client: Client, dump: dict) -> None:
    """The faculty roster, then one detail request per person.

    374 requests at the standard delay, so this is the slowest thing discover
    does. It is still the right place for it: every other API fetch lives here,
    and the dump is what makes rebuilding free. Nobody pays this cost twice
    unless they delete the dump.

    A person whose detail request fails keeps their roster row. The roster
    already carries name, department, position and work email, so a failure
    costs the profile prose rather than the person.
    """
    # One request per status. Asking without a status returns current staff only
    # and looks complete, which is how 8 people were missed on the first pass.
    rows: list[dict] = []
    seen: set[str] = set()
    for status in config.FACULTY_STATUSES:
        url = f"{config.API}{config.FACULTY_LIST}&employee_status={status}"
        try:
            listing = client.get_json(url)
        except Exception as exc:                     # noqa: BLE001
            log.warning("faculty roster (%s) FAILED: %s", status, exc)
            continue
        found = listing.get("data") if isinstance(listing, dict) else None
        found = [r for r in found if isinstance(r, dict)] if isinstance(found, list) else []
        new_rows = [r for r in found if r.get("slug") and r["slug"] not in seen]
        seen.update(r["slug"] for r in new_rows)
        rows.extend(new_rows)
        log.info("faculty roster %-10s %3d people", status, len(found))

    if not rows:
        log.warning("faculty roster empty - no faculty documents")
        dump["_faculty"] = {"error": "roster empty for every status"}
        return
    log.info("faculty roster: %d people across %d status(es)",
             len(rows), len(config.FACULTY_STATUSES))

    details: dict[str, object] = {}
    for i, row in enumerate(rows, 1):
        slug = row.get("slug")
        if not slug:
            continue
        url = f"{config.API}{config.FACULTY_DETAIL.format(slug=encode_slug(slug))}"
        try:
            details[slug] = client.get_json(url)
        except Exception as exc:                     # noqa: BLE001
            details[slug] = {"error": f"{type(exc).__name__}: {exc}"}
            log.warning("faculty %s FAILED: %s", slug, exc)
        if i % 50 == 0:
            log.info("faculty details %d/%d", i, len(rows))
    dump["_faculty"] = {"list": rows, "details": details}
    log.info("faculty: %d rosters, %d details fetched", len(rows), len(details))


def _fetch_alumni(client: Client, dump: dict) -> None:
    """Fetch the alumni site's own API. Spec §13 Q9, answered 2026-09-09.

    Kept in a separate namespace (`_alumni`) rather than merged into `dump`,
    because these paths come off a DIFFERENT host that happens to share some
    route names. `/alumni-settings` here and `/general-settings` there are both
    "the CMS settings", and flattening them into one dictionary would let the
    alumni site quietly overwrite the university's own data on any future name
    collision.

    A failure here never stops the run even for a `required` endpoint. The
    alumni site is one portion of the corpus; the university's own site is all
    the others, and a dead vendor host should not take them down with it.
    """
    results: dict[str, object] = {}
    for endpoint in config.ALUMNI_ENDPOINTS:
        url = f"{config.ALUMNI_API}{endpoint.path}"
        try:
            response = client.get(url)
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            results[endpoint.path] = {
                "status": response.status,
                "note": endpoint.note,
                "body": json.loads(response.content.decode("utf-8")),
            }
            log.info("alumni   %-46s %7d bytes", endpoint.path, len(response.content))
        except Exception as exc:                     # noqa: BLE001
            results[endpoint.path] = {"status": None,
                                      "error": f"{type(exc).__name__}: {exc}"}
            log.warning("alumni %s FAILED (%s) - continuing", endpoint.path, exc)
    dump["_alumni"] = results


def build_url_plan(dump: dict) -> list[tuple[str, str]]:
    """The residual crawl plan: only what stage 2 cannot produce from JSON.

    Returns (url, reason) pairs. The reason is written into urls.txt beside each
    entry because "no endpoint found" and "listing page, items already captured"
    are different situations with different fixes, and a bare URL list cannot
    tell them apart six months later. Spec §6.9.
    """
    planned: dict[str, str] = {}

    def add(url: str, why: str) -> None:
        url = canonical(url)
        if is_excluded_url(url):
            log.debug("plan: excluded %s", url)
            return
        planned.setdefault(url, why)          # first reason wins, insertion order kept

    for path, why in config.STATIC_ROUTES:
        add(f"{config.SITE}{path}", why)

    # Head profiles are NO LONGER planned here, and the reason is worth keeping.
    #
    # This loop used to plan 30 URLs, one per entity head, because that was the
    # only way to reach a faculty member's page. The API endpoint behind those
    # pages was found on 2026-09-09 and returns all 374 faculty, so the same 30
    # people are now built from JSON along with the other 344.
    #
    # Rendering them as well produced 28 documents claimed by two portions - the
    # same person, same URL, same id, from two sources. The API copy wins: it is
    # the same content without the 12,000 characters of navigation and footer
    # that the rendered page wraps around it.
    #
    # See builders/academic.build_faculty_members.

    for entity in _entities(dump):
        if entity.get("type") != "academic":
            continue
        slug = entity.get("slug")
        if not slug:
            continue
        for template in config.DEPT_SUBPAGE_TEMPLATES:
            add(f"{config.SITE}{template.format(slug=encode_slug(slug))}",
                "per-department page with no API coverage")

        for template in config.DEPT_ACADEMIC_TEMPLATES:
            add(f"{config.SITE}{template.format(slug=encode_slug(slug))}",
                "per-department academic page; verified real for EEE")

    for path, why in config.ALUMNI_STATIC_ROUTES:
        add(f"{config.ALUMNI_SITE}{path}", why)

    for url in config.EXTERNAL_ENTRY_POINTS:
        add(url, "separate host; not scanned for an API of its own (spec §13 Q9)")

    return list(planned.items())
