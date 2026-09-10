"""Portion `general`: the Facilities menu — the Downloads library.

On the website: /downloads, linked from both the Facilities menu and the
Notices menu, and again from the footer as "Downloadable Forms".

Source: `/downloads?search=&download_type_slug=&administrative_department_id=`.

That endpoint was NOT in the original seventeen and was not found by grep. The
frontend builds the call with its three filter parameters attached, so a
quoted-string search of the JS bundles misses it — the same failure mode
ENTITY_DETAIL records. It was found by opening the page and reading the Network
tab, which is the check worth repeating on any page that renders a table.

`/download-types` is a different thing and is not sufficient: it returns the two
category labels and nothing else. The file rows are only here.

The three parameters are the table's filter controls, not pagination. The page
sends all three empty and gets all 133 rows in one response, so there is no page
loop to write.

Owner: see the portion registry.
"""

from __future__ import annotations

import logging
import re

from .. import config
from ..paths import canonical, is_image_url
from .base import Document, Stage2Result, _rows

log = logging.getLogger(__name__)

# The endpoint key carries its query string, and that string is a filter the
# site may well change. Matching on the path prefix means a changed filter does
# not silently produce zero documents.
_DOWNLOADS_PREFIX = "/downloads"

# The real page every one of these documents cites. There is no per-type route:
# the site filters the same table in place, so /downloads is the only URL a
# reader can actually open. Fabricating /downloads/notice-app would 404.
_LISTING_PATH = "/downloads"


def _downloads_block(dump: dict):
    """The dump key for /downloads, whatever query string it was fetched with."""
    for key in dump:
        if key.split("?")[0] == _DOWNLOADS_PREFIX:
            return dump[key]
    return None


def build_downloads(dump: dict, result: Stage2Result) -> None:
    """133 downloadable files. Verified 2026-09-09.

    **One document per download type, holding an index table — not one document
    per file.** Same reasoning as `build_notices`, and for the same reason: a
    row here is a title, a department and a PDF link, with no prose of its own.
    133 separate documents would be 133 near-identical vectors, every one of
    them repeating "Type: Downloads", and each would fall under Team B's
    200-character `--min-text-chars` default anyway.

    The substance is in the PDFs, and those are recorded into `found_files` with
    `download: True` — a form's own text is what answers "what does the
    transcript application ask for", and that text arrives at extract time, not
    here.

    Rows are sorted by department within each document. Chunking then cuts along
    department boundaries rather than across them, so a chunk holds all six
    Controller of Examinations forms instead of a slice of six unrelated ones.
    The listing has no date field to sort on, which is what makes department the
    useful axis; `build_notices` sorts by date for the same reason in reverse.
    """
    block = _downloads_block(dump)
    if block is None:
        log.warning("/downloads not in the dump; no download documents. "
                    "Is the endpoint still in config.ENDPOINTS?")
        result.warnings.append("downloads_endpoint_missing")
        return

    rows = _rows(block)
    if not rows:
        log.warning("/downloads returned no rows")
        result.warnings.append("downloads_empty")
        return

    listing_url = f"{config.SITE}{_LISTING_PATH}"

    by_type: dict[str, list[dict]] = {}
    for row in rows:
        by_type.setdefault(row.get("download_type_title") or "Downloads", []).append(row)

    written = skipped = 0

    for type_title, type_rows in by_type.items():
        # Record every file first, whether or not it ends up in a table row.
        for row in type_rows:
            url = row.get("file")
            if not url:
                # A catalogued file with no link. Worth a warning rather than a
                # silent skip: it is the site's own broken row, and the title
                # tells a reader the document exists.
                log.warning("download %r has no file url", row.get("title"))
                result.warnings.append(f"download_no_file:{row.get('id')}")
                skipped += 1
                continue
            if is_image_url(url):
                skipped += 1
                continue

            key = canonical(url)
            record = result.found_files.setdefault(key, {
                "url": key,
                "linked_from": [],
                "document_type": "download",
                "title": row.get("title") or f"Download {row.get('id')}",
                "category": type_title,
                "department": row.get("administrative_department_title"),
                "download": True,
            })
            record["download"] = True
            if listing_url not in record["linked_from"]:
                record["linked_from"].append(listing_url)

        listed = [r for r in type_rows if r.get("file") and not is_image_url(r["file"])]
        listed.sort(key=lambda r: (
            str(r.get("administrative_department_title") or "zzz"),
            str(r.get("title") or ""),
        ))

        pages = [listed[i:i + config.DOWNLOADS_PER_DOCUMENT]
                 for i in range(0, len(listed), config.DOWNLOADS_PER_DOCUMENT)] or [[]]

        slug = re.sub(r"[^a-z0-9]+", "-", type_title.lower()).strip("-")

        for index, page in enumerate(pages, start=1):
            suffix = f" ({index} of {len(pages)})" if len(pages) > 1 else ""
            title = f"{type_title}{suffix}"

            # A query parameter, never a #fragment: canonical() strips fragments
            # before page_id hashes, so a #part-2 suffix collapses every part
            # onto one id. See Document's docstring.
            key = f"{listing_url}?_type={slug}&_part={index}"

            body = [
                f"<h1>{title}</h1>",
                f"<p>CUET publishes {len(listed)} downloadable files under "
                f"&ldquo;{type_title}&rdquo; — forms, curricula, official lists "
                f"and manuals. Each row below links a file that is downloaded to "
                f"<code>_files/</code>.</p>",
                "<table><tr><th>Title</th><th>Department</th></tr>",
            ]
            for row in page:
                body.append(
                    "<tr>"
                    f"<td>{row.get('title') or ''}</td>"
                    f"<td>{row.get('administrative_department_title') or ''}</td>"
                    "</tr>"
                )
            body.append("</table>")

            result.documents.append(Document(
                url=listing_url,
                key=key,
                title=title,
                html="\n".join(body),
                section="resources",
                group="downloads",
                section_path=["Downloads", type_title],
                extra={
                    "download_type": type_title,
                    "download_count": len(page),
                    "download_ids": [r.get("id") for r in page],
                    "listing_url": listing_url,
                },
            ))
            written += 1

    log.info("downloads: %d files across %d types, %d index documents, %d skipped",
             len(rows), len(by_type), written, skipped)