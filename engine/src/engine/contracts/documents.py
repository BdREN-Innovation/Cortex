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
