"""Stage 6: re-derive the API endpoint inventory from the live site. Spec §6.12.

Every finding in the 2026-09-08 revision came from running this by hand. Twelve
endpoints existed while the spec confidently said there were four, and nothing
in the pipeline would ever have noticed: the crawl would have succeeded,
produced plausible output, and silently missed most of the site.

A capture pipeline only detects the failures it was told to look for. This is
the stage that looks for the failure of *not knowing what exists*.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from . import config
from .api import Client

log = logging.getLogger(__name__)

_CHUNK_RE = re.compile(r"static/chunks/[^\"'\\\s]+?\.js")
_ENDPOINT_RE = re.compile(r"/api/v1/[a-zA-Z0-9_-]+")

# Pages whose bundles are scanned. Chosen to span the route families: a listing,
# a dynamic detail route, the layout, and one page per in-scope section.
AUDIT_PAGES = (
    "", "departments", "department/cse", "news-events",
    "academic-information/academic-calendars", "admission",
    "institutes", "centers", "faculty", "notices/noc",
    "student/organizations", "research/journal-paper", "apa", "downloads",
)


def run(client: Client, out: Path | None = None) -> dict:
    out = out or config.OUT
    meta = out / "_meta"
    meta.mkdir(parents=True, exist_ok=True)

    chunks: set[str] = set()
    for page in AUDIT_PAGES:
        url = f"{config.SITE}/{page}"
        try:
            # The one useful thing the RSC header does. It returns a real Flight
            # payload — no page data, but it lists the page's JS chunks, and the
            # chunks carry the endpoint strings. Spec §3.0, §13 Q1.
            response = client.get(url, headers={"RSC": "1"})
            found = set(_CHUNK_RE.findall(response.text))
            chunks |= found
            log.info("audit %-44s %2d chunks", f"/{page}", len(found))
        except Exception as exc:                     # noqa: BLE001
            log.warning("audit page %s failed: %s", url, exc)

    endpoints: set[str] = set()
    for chunk in sorted(chunks):
        try:
            # A chunk name contains a content hash, so a cached response can
            # never be stale: if the file changed, its name changed. Without
            # caching this re-downloads ~40 identical files every run, which is
            # the impoliteness §7.4 forbids.
            body = _cached_chunk(client, chunk, out)
            endpoints |= set(_ENDPOINT_RE.findall(body))
        except Exception as exc:                     # noqa: BLE001
            log.warning("audit chunk %s failed: %s", chunk, exc)

    known = {e.path.split("?")[0] for e in config.ENDPOINTS}
    known.add(config.ENTITY_DETAIL.split("{")[0].rstrip("/"))
    found = {e.replace("/api/v1", "") for e in endpoints}

    undocumented = sorted(f for f in found if f not in known)
    unreferenced = sorted(k for k in known if k not in found)

    report = {
        "pages_scanned": len(AUDIT_PAGES),
        "chunks_scanned": len(chunks),
        "endpoints_found": sorted(found),
        "undocumented": undocumented,
        "unreferenced_by_any_scanned_page": unreferenced,
    }
    (meta / "endpoints.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if undocumented:
        log.warning("AUDIT: %d endpoint(s) the config does not know about: %s",
                    len(undocumented), ", ".join(undocumented))
        log.warning("The inventory in spec §3.0 is stale. Update it before "
                    "trusting a capture built on it.")
    else:
        log.info("audit: no undocumented endpoints; the inventory is current")

    if unreferenced:
        # Not necessarily wrong: an endpoint may be used by a page outside
        # AUDIT_PAGES. Reported so a human can judge, not treated as an error.
        log.info("audit: %d configured endpoint(s) not referenced by the scanned "
                 "pages (may be used elsewhere): %s",
                 len(unreferenced), ", ".join(unreferenced))

    return report


def _cached_chunk(client: Client, chunk: str, out: Path) -> str:
    cache = out / "_meta" / "chunk_cache"
    cache.mkdir(parents=True, exist_ok=True)
    key = cache / chunk.replace("/", "_")
    if key.exists():
        return key.read_text(encoding="utf-8", errors="replace")
    response = client.get(f"{config.SITE}/_next/{chunk}")
    body = response.text
    key.write_text(body, encoding="utf-8")
    return body
