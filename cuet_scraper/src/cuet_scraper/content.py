"""Stage 2: turn the API payloads into documents.

After the 2026-09-08 revision this is where most of the corpus comes from —
roughly 530 documents from about 45 requests, with no browser. Spec §6.8.

Every source writes the same three-file shape, so a consumer cannot tell a
JSON-derived document from a browser-captured one except by reading `source`.
That uniformity is deliberate: downstream code should not branch on provenance.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from engine.contracts.documents import CleanDocument, content_hash

from . import config
from .markdown import to_markdown, unescape_once
from .paths import (canonical, is_excluded_url, is_image_url, looks_like_file,
                    page_id, safe_name)

log = logging.getLogger(__name__)

_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_SRC_RE = re.compile(r'src=["\']([^"\']+)["\']', re.I)
# Bare document URLs, for files that appear in text rather than inside an <a>.
_FILE_URL_RE = re.compile(
    r'https?://[^\s"\'<>]+?\.(?:pdf|docx?|xlsx?|pptx?|zip|csv)', re.I
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Document:
    """One captured document, before it is written to disk.

    `url` and `key` are separate on purpose.

    * **`url` is what a citation shows a reader**, so it must be a page that
      actually resolves on cuet.ac.bd.
    * **`key` is what the document is identified by** — it becomes `doc_id` and
      the filename.

    They differ only where one real page yields several documents: the 265 NOC
    notices are one listing page but five index documents, and those five need
    distinct ids while still citing the page a reader can open. Defaulting `key`
    to `url` keeps the ordinary case a single value.

    **A key must survive canonicalisation.** `page_id()` canonicalises before
    hashing and `canonical()` strips fragments (spec §6.3), so a `#part-2`
    suffix silently collapses every part onto one id — which is exactly what
    happened on the first run here. Use a query parameter instead;
    canonicalisation preserves those. `_part` is named with a leading
    underscore to mark it as ours rather than something the site would accept.
    """
    url: str
    title: str
    html: str
    section: str
    group: str
    section_path: list[str]
    key: str = ""
    source: str = "api"
    extra: dict = field(default_factory=dict)
    files: list[dict] = field(default_factory=list)
    double_escaped: bool = False

    def __post_init__(self) -> None:
        if not self.key:
            self.key = self.url


@dataclass
class Stage2Result:
    documents: list[Document] = field(default_factory=list)
    found_files: dict[str, dict] = field(default_factory=dict)
    found_pages: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)   # written metadata records


# --------------------------------------------------------------------------
# Link and file harvesting
# --------------------------------------------------------------------------

def harvest(html: str, base: str, result: Stage2Result, *,
            linked_from: str, meta: dict | None = None) -> list[dict]:
    """Pull links and document URLs out of a block of HTML.

    CMS HTML contains real URLs the navigation never shows — `/admission/msc/`,
    `admissionckruet.ac.bd`, and the vendor domain from spec §4.11 — so the same
    filtering pipeline runs over it. Spec §6.8.

    Returns the document links found, and records everything in `result`.
    """
    files: list[dict] = []
    if not html:
        return files

    candidates = set(_HREF_RE.findall(html)) | set(_SRC_RE.findall(html))
    candidates |= set(_FILE_URL_RE.findall(html))

    for raw in candidates:
        raw = raw.strip()
        # Filter by scheme before anything tries to fetch. The page carries
        # href="#" on every dropdown toggle, plus mailto:undefined and
        # tel:undefined, which are the site's own bugs. Spec §4.8.
        if not raw or raw.startswith(("#", "javascript:", "data:")):
            continue
        if raw.startswith(("mailto:", "tel:")):
            continue

        url = canonical(urljoin(base, raw))
        parts = url.split("://", 1)
        if len(parts) != 2 or not parts[0].startswith("http"):
            continue

        # Images are refused here rather than later. Note that CMS HTML holds
        # RELATIVE image paths such as /assets/images/undergraduate.jpg, which
        # only look like images after being resolved against the base. Spec §4.6.
        if is_image_url(url):
            continue
        if is_excluded_url(url):
            continue

        if looks_like_file(url):
            record = result.found_files.setdefault(
                url, {"url": url, "linked_from": [], **(meta or {})}
            )
            # linked_from accumulates: the same PDF is linked from many pages.
            # Overwriting would lose every source but the last. Part 2 §12.3.
            if linked_from not in record["linked_from"]:
                record["linked_from"].append(linked_from)
            files.append({"url": url})
        else:
            result.found_pages.add(url)

    return files


def _clean_html(value: str, result: Stage2Result, label: str) -> tuple[str, bool]:
    """Return (html, was_double_escaped). Spec §3.3, §6.8."""
    if value and any(marker in value for marker in config.DOUBLE_ESCAPE_MARKERS):
        log.warning("double-escaped CMS value: %s (unescaping once)", label)
        result.warnings.append(f"double_escaped:{label}")
        return unescape_once(value), True
    return value or "", False


# --------------------------------------------------------------------------
# Builders, one per API source
# --------------------------------------------------------------------------

def _body(block) -> dict | list | None:
    if isinstance(block, dict) and "body" in block:
        return block["body"]
    return None


def _rows(block, key: str = "data") -> list[dict]:
    body = _body(block)
    if isinstance(body, dict):
        rows = body.get(key)
    elif isinstance(body, list):
        rows = body
    else:
        rows = None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _setting_value(settings: dict, key: str) -> str:
    """Read one /general-settings value.

    VERIFIED 2026-09-08: every setting is wrapped as `{"id", "key", "value"}`,
    with the HTML in `value` — NOT a bare string as spec §3.3 describes. The
    plain-string form is still accepted here in case the wrapper is a newer
    addition and an older dump is replayed.
    """
    raw = settings.get(key)
    if isinstance(raw, dict):
        raw = raw.get("value")
    return raw if isinstance(raw, str) else ""


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


def build_news(dump: dict, result: Stage2Result) -> None:
    """157 news items with full HTML bodies. Spec §4.9."""
    for row in _rows(dump.get("/news")):
        nid = row.get("id")
        if nid is None:
            continue
        url = f"{config.SITE}/news/{nid}"
        html, escaped = _clean_html(row.get("description") or "", result, f"news.{nid}")
        doc = Document(
            url=url, title=row.get("title") or f"News {nid}", html=html,
            section="news-events", group="news",
            section_path=["News & Events", "News", row.get("title") or str(nid)],
            extra={"news_id": nid, "date": row.get("date")},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.SITE, result, linked_from=url,
                            meta={"document_type": "news",
                                  "published_date": row.get("date")})
        result.documents.append(doc)


def build_events(dump: dict, result: Stage2Result) -> None:
    for row in _rows(dump.get("/events")):
        eid = row.get("id")
        if eid is None:
            continue
        url = f"{config.SITE}/event-details/{eid}"
        html, escaped = _clean_html(row.get("description") or "", result, f"event.{eid}")
        doc = Document(
            url=url, title=row.get("title") or f"Event {eid}", html=html,
            section="news-events", group="event-details",
            section_path=["News & Events", "Events", row.get("title") or str(eid)],
            extra={"event_id": eid, "from": row.get("from"), "to": row.get("to"),
                   "location": row.get("location"), "link": row.get("link")},
            double_escaped=escaped,
        )
        doc.files = harvest(html, config.SITE, result, linked_from=url,
                            meta={"document_type": "event"})
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
                extra={"notice_type": type_title,
                       "notice_count": len(page),
                       "notice_ids": [r.get("id") for r in page],
                       "listing_url": listing_url,
                       "in_scope": scoped},
            ))

    log.info("notices: %d in scope, %d out of scope; %d index documents",
             in_scope, out_of_scope,
             sum(1 for d in result.documents if d.group == "notices"))


BUILDERS = (build_cms, build_entities, build_news, build_events,
            build_student_organizations, build_curricula, build_notices)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def write_document(doc: Document, out: Path) -> dict:
    """Write the .html / .md / .json triple atomically. Spec §6.5, §7.3.

    Order is html, md, json — the JSON is the completion marker for
    resumability, so it goes last. Spec §7.1.
    """
    folder = out / doc.section / doc.group if doc.group else out / doc.section
    folder.mkdir(parents=True, exist_ok=True)

    doc_id = page_id(doc.key)
    # Slug from the PATH only. The key may carry synthetic query parameters
    # (see Document) and those belong in the id, not in the filename.
    slug = safe_name(
        doc.key.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "index",
        keep_extension=False,
    )
    stem = f"{slug}__{doc_id[:8]}"

    text = to_markdown(doc.html)
    html_path = folder / f"{stem}.html"
    md_path = folder / f"{stem}.md"
    json_path = folder / f"{stem}.json"

    # HTML as BYTES, not decoded text. A decoding mistake stays recoverable;
    # a mis-decoded save is only fixable by re-crawling. Spec §4.12.
    _atomic_write_bytes(html_path, doc.html.encode("utf-8"))
    _atomic_write_bytes(md_path, text.encode("utf-8"))

    meta = {
        "url": doc.url,
        "canonical_url": canonical(doc.url),
        "page_id": doc_id,
        "doc_key": doc.key,
        "section": doc.section,
        "group": doc.group,
        "section_path": doc.section_path,
        "title": doc.title,
        "source": doc.source,
        "status": 200,
        "fetched_at": _now(),
        "html_path": str(html_path.relative_to(out)).replace("\\", "/"),
        "markdown_path": str(md_path.relative_to(out)).replace("\\", "/"),
        "text_chars": len(text),
        "render_ok": True,
        "attempts": 1,
        "links_found": len(doc.files),
        "double_escaped": doc.double_escaped,
        "files": doc.files,
        **doc.extra,
    }
    _atomic_write_bytes(
        json_path, json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
    )
    meta["_text"] = text
    meta["_json_path"] = json_path
    return meta


def _atomic_write_bytes(dest: Path, payload: bytes) -> None:
    """Write via a .part file and rename. Spec §7.3.

    Without this, an interrupt mid-write leaves a truncated file that the resume
    check counts as complete, and the corruption stays invisible until something
    downstream fails.
    """
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(payload)
    tmp.replace(dest)


def to_clean_document(meta: dict) -> CleanDocument:
    """A CleanDocument row for API-derived content. Spec §12.1.

    Deliberate deviation, stated rather than slipped in: CrawledPage carries no
    text because HTML needs cleaning and that is Team B's job. API content
    arrives as prose with no navigation, banner or footer to strip, so the
    extraction step would have nothing to do.
    """
    text = meta["_text"]
    return CleanDocument(
        doc_id=meta["page_id"],
        source_url=meta["url"],
        canonical_url=meta["canonical_url"],
        title=meta["title"],
        text=text,
        content_hash=content_hash(text),
        fetched_at=meta["fetched_at"],
        section_path=meta["section_path"],
        html_path=meta["html_path"],
        lang="en",
        doc_type="page",
        meta={"source": meta["source"], "section": meta["section"]},
    )


def run(dump: dict, out: Path | None = None) -> Stage2Result:
    """Build and write every API-derived document."""
    out = out or config.OUT
    result = Stage2Result()

    for builder in BUILDERS:
        before = len(result.documents)
        builder(dump, result)
        log.info("%-28s produced %4d documents", builder.__name__, len(result.documents) - before)

    meta_dir = out / "_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for doc in result.documents:
        # A document whose HTML yields no text is not a document. This happens
        # for records that carry only a banner image, and for events whose
        # description is an empty <p>. Dropping them here beats writing a row
        # that fails CleanDocument.validate() downstream — and it is NOT the
        # thin-page filtering spec §4.4 forbids, because the raw payload is
        # still in _meta/api_dump.json and nothing has been discarded.
        if not to_markdown(doc.html).strip():
            log.info("skipping %s: no text after conversion", doc.key)
            result.warnings.append(f"empty_document:{doc.key}")
            continue
        rows.append(write_document(doc, out))

    with (out / "documents.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            clean = to_clean_document(row)
            problems = clean.validate()
            if problems:
                log.warning("CleanDocument %s invalid: %s", clean.doc_id, problems)
                result.warnings.append(f"invalid_document:{clean.doc_id}")
                continue
            handle.write(json.dumps(clean.__dict__, ensure_ascii=False,
                                    default=str) + "\n")

    (meta_dir / "found_files.txt").write_text(
        "\n".join(sorted(result.found_files)) + "\n", encoding="utf-8")
    (meta_dir / "found_files.json").write_text(
        json.dumps(list(result.found_files.values()), ensure_ascii=False, indent=2),
        encoding="utf-8")
    (meta_dir / "found_pages.txt").write_text(
        "\n".join(sorted(result.found_pages)) + "\n", encoding="utf-8")

    # The run-directory shape engine extract expects, plus a README explaining
    # this corpus to whoever embeds it. See handover.py.
    from . import handover
    from datetime import datetime, timezone
    pages = handover.write_all(
        out, rows,
        run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        started=_now(),
    )

    result.rows = rows
    log.info("content: %d documents (%d CrawledPage rows), "
             "%d files discovered, %d pages discovered",
             len(rows), pages, len(result.found_files), len(result.found_pages))
    return result
