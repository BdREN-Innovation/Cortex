"""Portion `general`: the Research menu — publications by type.

On the website: /research/journal-paper, /research/conference-paper,
/research/partnership and /research/mou.

Source: `/app-admin-research-types`. One request returns all four types with
their publications nested, so there is no per-type call and no page loop.

VERIFIED 2026-09-09:

    journal-paper       1358
    conference-paper     202
    partnership            0
    mou                    0

Not covered here, and covered elsewhere:

* **/research/research-highlights** and **/research/research-area** are CMS page
  bodies, in CMS_CONTENT_KEYS and emitted by `build_cms`. They are prose about
  research, not a list of publications, and they have no rows here.
* **/research/others** is in the site's Research menu and is NOT one of the four
  types this endpoint returns. It has no known source.
"""

from __future__ import annotations

import logging

from .. import config
from ..paths import canonical, in_allowed_host, is_image_url, looks_like_file
from .base import Document, Stage2Result, _clean_html, _rows, harvest

log = logging.getLogger(__name__)

_RESEARCH_PATH = "/research"


def build_research(dump: dict, result: Stage2Result) -> None:
    """1,560 publications across 4 types. Verified 2026-09-09.

    **Index tables, not one document per publication.** Same reasoning as
    `build_notices` and `build_downloads`: a publication row is a citation
    string and a DOI. 1,560 of them as separate documents would be 1,560
    near-identical vectors, each under Team B's `--min-text-chars` default, and
    every one citing the same listing page because a publication has no page of
    its own on this site.

    Rows are sorted by author within each document, so chunking cuts along
    author boundaries: a chunk holds one person's papers rather than a slice of
    twenty unrelated ones. `admin_name` is the join back to the faculty
    documents the academic portion emits from /app-admins, which is what makes
    "what has this person published" answerable at all.

    A type with no publications still gets a document. Partnership and Mou both
    return zero rows, and their pages are real: the type's `description` is page
    content, and a corpus that cannot say CUET lists no MoUs is worse than one
    that can. Spec §4.4 — thin-page filtering is Team B's decision, downstream
    and reversible.

    The `description` on journal-paper is CSE-department text on a
    university-wide page. That is the site's own copy-paste error, captured
    verbatim: the corpus records what CUET publishes, not what it meant.
    """
    types = _rows(dump.get("/app-admin-research-types"))
    if not types:
        log.warning("/app-admin-research-types returned no types")
        result.warnings.append("research_types_empty")
        return

    written = files_found = 0

    for entry in types:
        slug = entry.get("slug")
        if not slug:
            log.warning("research type %r has no slug; skipped", entry.get("title"))
            result.warnings.append(f"research_type_no_slug:{entry.get('id')}")
            continue

        type_title = entry.get("title") or slug
        url = f"{config.SITE}{_RESEARCH_PATH}/{slug}"

        description, escaped = _clean_html(
            entry.get("description") or "", result, f"research.{slug}"
        )

        publications = [p for p in (entry.get("app_admin_researches") or [])
                        if isinstance(p, dict)]
        publications.sort(key=lambda p: (
            str(p.get("admin_name") or "zzz"),
            str(p.get("date") or ""),
        ))

        # A publication's `file` is occasionally a PDF CUET hosts itself. The
        # `url` and `doi_url` fields are publisher and Google Scholar links —
        # someone else's server, out of scope, and not ours to download. So the
        # host check is the filter, not the extension.
        for pub in publications:
            candidate = pub.get("file")
            if not candidate or is_image_url(candidate):
                continue
            key = canonical(candidate)
            if not (in_allowed_host(key) and looks_like_file(key)):
                continue
            record = result.found_files.setdefault(key, {
                "url": key,
                "linked_from": [],
                "document_type": "publication",
                "title": pub.get("title") or f"Publication {pub.get('id')}",
                "published_date": pub.get("date"),
                "category": type_title,
                "author": pub.get("admin_name"),
                "download": True,
            })
            record["download"] = True
            if url not in record["linked_from"]:
                record["linked_from"].append(url)
            files_found += 1

        pages = [publications[i:i + config.RESEARCH_PER_DOCUMENT]
                 for i in range(0, len(publications), config.RESEARCH_PER_DOCUMENT)]
        # An empty type still yields one document, carrying the description.
        pages = pages or [[]]

        for index, page in enumerate(pages, start=1):
            suffix = f" ({index} of {len(pages)})" if len(pages) > 1 else ""
            title = f"{type_title}{suffix}"

            body = [f"<h1>{title}</h1>"]

            # The description belongs on the first part only: repeating it on
            # all 23 journal-paper documents would put the same paragraph in 23
            # chunks, which is the duplication the index-table approach exists
            # to avoid.
            if index == 1 and description.strip():
                body.append(description)

            if page:
                body.append(
                    f"<p>CUET records {len(publications)} entries under "
                    f"&ldquo;{type_title}&rdquo;.</p>"
                )
                body.append("<table><tr><th>Author</th><th>Publication</th>"
                            "<th>Year</th><th>DOI</th></tr>")
                for pub in page:
                    # vancouver_title is the formatted citation the site itself
                    # renders; `title` holds the same string less consistently.
                    citation = pub.get("vancouver_title") or pub.get("title") or ""
                    body.append(
                        "<tr>"
                        f"<td>{pub.get('admin_name') or ''}</td>"
                        f"<td>{citation}</td>"
                        f"<td>{pub.get('date') or ''}</td>"
                        f"<td>{pub.get('doi_no') or ''}</td>"
                        "</tr>"
                    )
                body.append("</table>")
            else:
                body.append(
                    f"<p>CUET publishes a &ldquo;{type_title}&rdquo; page, and it "
                    f"currently lists no entries.</p>"
                )

            html = "\n".join(body)
            doc = Document(
                url=url,
                # Query parameter, never a #fragment: canonical() strips
                # fragments before page_id hashes, collapsing every part onto
                # one id. See Document's docstring.
                key=f"{url}?_part={index}" if len(pages) > 1 else url,
                title=title,
                html=html,
                section="research",
                group="publications",
                section_path=["Research", type_title],
                extra={
                    "origin": "API /app-admin-research-types",
                    "research_type": type_title,
                    "research_slug": slug,
                    "publication_count": len(page),
                    "publication_total": len(publications),
                    "authors": sorted({p.get("admin_name") for p in page
                                       if p.get("admin_name")}),
                },
                double_escaped=escaped,
            )
            # The description routinely links out; harvest catches anything
            # CUET hosts and ignores the rest.
            doc.files = harvest(html, config.SITE, result, linked_from=url,
                                meta={"document_type": "research"})
            result.documents.append(doc)
            written += 1

    log.info("research: %d types, %d index documents, %d hosted files",
             len(types), written, files_found)