"""What the crawler produces and the knowledge base consumes.

`CleanDocument` is the single most important schema in the engine: as long as the
crawler keeps emitting it, team 1 can rewrite its internals freely and team 2
never notices.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


def content_hash(text: str) -> str:
    """Stable hash of page text, used to skip re-embedding unchanged pages."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def make_doc_id(canonical_url: str) -> str:
    """Stable id for a page, independent of crawl order or run."""
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RawPage:
    """Exactly what came back over HTTP. Kept so extraction can be re-run offline."""

    url: str
    status: int
    html: str
    headers: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=_utcnow)
    elapsed_ms: int = 0


# What `CleanDocument.doc_type` may hold. A row is always text the knowledge
# team can chunk; the type only says where that text came from.
DOC_TYPES = ("page", "pdf")

# What `Asset.kind` may hold. Assets are the *binary* things a page carried —
# never text, never chunked. `table` is deliberately absent: tables are folded
# into the page text so they get embedded with their surrounding context, and
# only mirrored to disk for inspection.
ASSET_KINDS = ("image", "document", "table")


@dataclass
class Asset:
    """A non-text file a page carried, saved beside documents.jsonl.

    Images are captured but *not* consumed by the knowledge team: the embedders
    are text-only, so a PNG has no path to an answer. They are kept so a future
    multimodal pass has something to work from.
    """

    kind: str  # one of ASSET_KINDS
    path: str  # on-disk location, relative to the run directory
    source_url: str  # where it was downloaded from
    ordinal: int = 0  # position within its page, so order survives
    alt: str = ""  # image alt text / table caption — this *is* searchable
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "path": self.path,
            "source_url": self.source_url,
            "ordinal": self.ordinal,
            "alt": self.alt,
            "meta": self.meta,
        }


@dataclass
class RawAsset:
    """Exactly what came back for a non-HTML URL: a PDF, an image, a spreadsheet."""

    url: str
    status: int
    content: bytes
    content_type: str = ""
    fetched_at: datetime = field(default_factory=_utcnow)
    elapsed_ms: int = 0


@dataclass
class CrawledPage:
    """What the crawl team captures, and the only thing they hand over.

    This is the crawler -> knowledge handoff. It deliberately contains **no
    text**: capture and interpretation are separate jobs, so that re-reading a
    site costs a second of local work instead of another polite crawl of
    somebody else's server.

    `content_path` points at bytes on disk — HTML for a page, the file itself
    for a PDF. Everything downstream re-reads from there.
    """

    page_id: str
    url: str
    canonical_url: str
    status: int
    content_type: str
    content_path: str  # relative to the run directory
    fetched_at: str
    depth: int = 0
    # Structural discovery, done by the crawl team because the frontier needs
    # it anyway. Content extraction is emphatically *not* here.
    links: list[str] = field(default_factory=list)
    document_links: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    # Set when this page was reached as a linked file rather than a hyperlink.
    parent_url: str = ""
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict) -> "CrawledPage":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in payload.items() if k in known})

    def validate(self) -> list[str]:
        problems = []
        if not self.page_id:
            problems.append("page_id is empty")
        if not self.canonical_url:
            problems.append("canonical_url is empty")
        if not self.content_path:
            problems.append("content_path is empty")
        return problems


@dataclass
class CleanDocument:
    """One page, cleaned. The crawler -> knowledge handoff record."""

    doc_id: str
    source_url: str
    canonical_url: str
    title: str
    text: str
    content_hash: str
    fetched_at: str
    # Breadcrumb such as ["Docs", "Billing", "Refunds"]. Citations and the eval
    # harness both depend on this, so the crawler must always populate it.
    section_path: list[str] = field(default_factory=list)
    html_path: str = ""
    lang: str = "en"
    meta: dict = field(default_factory=dict)
    # "page" or "pdf". A linked PDF becomes its own row rather than being glued
    # onto the page that linked it, so it chunks and cites independently.
    doc_type: str = "page"
    # Binary companions to this row: {kind, path, source_url, ordinal, alt, meta}.
    # The knowledge team ignores these; they exist for provenance and for later.
    assets: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict) -> "CleanDocument":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in payload.items() if k in known})

    def validate(self) -> list[str]:
        problems = []
        if not self.doc_id:
            problems.append("doc_id is empty")
        if not self.canonical_url:
            problems.append("canonical_url is empty")
        if not self.text.strip():
            problems.append("text is empty")
        if self.content_hash != content_hash(self.text):
            problems.append("content_hash does not match text")
        if self.doc_type not in DOC_TYPES:
            problems.append(f"doc_type {self.doc_type!r} is not one of {DOC_TYPES}")
        for position, asset in enumerate(self.assets):
            if asset.get("kind") not in ASSET_KINDS:
                problems.append(f"assets[{position}].kind {asset.get('kind')!r} is invalid")
            if not asset.get("path"):
                problems.append(f"assets[{position}].path is empty")
        return problems


@dataclass
class Chunk:
    """A slice of a document, sized for embedding. Produced by the knowledge team."""

    chunk_id: str
    doc_id: str
    text: str
    ordinal: int
    canonical_url: str
    title: str = ""
    section_path: list[str] = field(default_factory=list)
    token_estimate: int = 0
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict) -> "Chunk":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class CrawlManifest:
    """Sits next to documents.jsonl and describes how the run went."""

    run_id: str
    site: str
    seeds: list[str]
    started_at: str
    finished_at: str
    pages_fetched: int
    pages_written: int
    pages_skipped: int
    errors: list[dict] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    # {"image": 12, "document": 3, "table": 7} — what the run captured besides prose.
    assets_saved: dict = field(default_factory=dict)
    # PDFs promoted to their own CleanDocument rows.
    documents_parsed: int = 0
