"""Portion `notices`: every notice type the site publishes.

On the website: the Notices menu and the top-bar notice links — /notices/noc,
/notices/scholarship-financial-aids, /notices/academic-calender and the catch-all
/notices/all-notice listing that the out-of-scope types share.

Owner: see `portions.py`.
"""

from __future__ import annotations

import logging
import re

from .. import config
from ..paths import canonical, is_image_url
from .base import Document, Stage2Result, _rows

log = logging.getLogger(__name__)


def build_notices(dump: dict, result: Stage2Result) -> None:
    """976 notices; 283 in scope for Part 1. Spec §3.6.

    **One document per notice type, holding an index table — not one document
    per notice.** This is a deliberate choice and the reasoning matters to
    whoever embeds this corpus.

    A notice has almost no prose of its own: its substance is the linked PDF,
    and its record is a title, a date, a type and a department. Emitting one
    document each would produce 265 texts differing only in a title and a date,
    every one of them repeating "Type: Offices Orders/NOC". Embedded, those
    become 265 near-identical vectors that crowd out real content in every
    retrieval, and they would then be dropped anyway by the 200-character
    `--min-text-chars` default (spec §12.2).

    An index table instead gives one coherent document per type: chunking splits
    it into runs of notice titles, each chunk is genuinely distinct, and a
    citation points at the real listing page a reader can open. The per-file
    metadata that makes a `<hash>.pdf` findable lives in `_files/index.json`,
    which is where a file index belongs. Part 2 §3.2 and §12.3.
    """
    by_type: dict[str, list[dict]] = {}
    for row in _rows(dump.get("/notices")):
        # Filter on notice_type_title, the DISPLAY string this endpoint returns.
        # /notice-types carries slugs; they are different strings and neither is
        # derivable from the other. Spec §3.6.
        by_type.setdefault(row.get("notice_type_title") or "Uncategorised", []).append(row)

    in_scope = out_of_scope = 0

    for type_title, rows in by_type.items():
        scope = config.NOTICE_TYPES_IN_SCOPE.get(type_title)
        scoped = scope is not None
        section, route = scope if scoped else ("_unsorted", "/notices/all-notice")

        # Every notice's PDF is recorded whether or not we intend to fetch it.
        # Recording that a file exists costs nothing; downloading 693 more PDFs
        # does. Two separate decisions, two separate switches. Part 2 §3.4.
        want_file = scoped or config.DOWNLOAD_OUT_OF_SCOPE_NOTICE_FILES
        listing_url = f"{config.SITE}{route}"

        for row in rows:
            pdf = row.get("pdf")
            if not pdf or is_image_url(pdf):
                continue
            key = canonical(pdf)
            record = result.found_files.setdefault(key, {
                "url": key, "linked_from": [], "document_type": "notice",
                "title": row.get("title") or f"Notice {row.get('id')}",
                "published_date": row.get("publish_date"),
                "category": type_title,
                "department": row.get("administrative_department_title"),
                "download": want_file,
            })
            record["download"] = record.get("download") or want_file
            if listing_url not in record["linked_from"]:
                record["linked_from"].append(listing_url)

        if scoped:
            in_scope += len(rows)
        else:
            out_of_scope += len(rows)
            if not config.CAPTURE_OUT_OF_SCOPE_NOTICE_METADATA:
                continue

        rows.sort(key=lambda r: str(r.get("publish_date") or ""), reverse=True)
        pages = [rows[i:i + config.NOTICES_PER_DOCUMENT]
                 for i in range(0, len(rows), config.NOTICES_PER_DOCUMENT)] or [[]]

        for index, page in enumerate(pages, start=1):
            suffix = f" ({index} of {len(pages)})" if len(pages) > 1 else ""
            title = f"{type_title} notices{suffix}"
            # Cite the real listing page; identify by an explicit key so the
            # parts of a split listing do not collide. See Document's docstring.
            url = listing_url
            # The type must be in the key too: every out-of-scope type shares
            # the /notices/all-notice listing, so without it Student Notices and
            # General Notices would collide on the same id.
            slug = re.sub(r"[^a-z0-9]+", "-", type_title.lower()).strip("-")
            key = f"{listing_url}?_type={slug}&_part={index}"
            body = [
                f"<h1>{title}</h1>",
                f"<p>CUET publishes {len(rows)} notices under "
                f"&ldquo;{type_title}&rdquo;. Each row below links the notice's "
                f"PDF, which is downloaded to <code>_files/</code>.</p>",
                "<table><tr><th>Date</th><th>Notice</th><th>Department</th></tr>",
            ]
            for row in page:
                body.append(
                    "<tr>"
                    f"<td>{row.get('publish_date') or ''}</td>"
                    f"<td>{row.get('title') or ''}</td>"
                    f"<td>{row.get('administrative_department_title') or ''}</td>"
                    "</tr>"
                )
            body.append("</table>")

            result.documents.append(Document(
                url=url, key=key, title=title, html="\n".join(body),
                section=section, group="notices",
                section_path=["Notices", type_title],
                extra={"origin": "API /notices + /notice-types",
                       "notice_type": type_title,
                       "notice_count": len(page),
                       "notice_ids": [r.get("id") for r in page],
                       "listing_url": listing_url,
                       "in_scope": scoped},
            ))

    log.info("notices: %d in scope, %d out of scope; %d index documents",
             in_scope, out_of_scope,
             sum(1 for d in result.documents if d.group == "notices"))

