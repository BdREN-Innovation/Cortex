# scratch/contracts_stub.py — DELETE once src/engine/contracts/ has the real
# CrawledPage / CleanDocument from Team A. Only exists so documents.py can be
# exercised end to end against fixtures/site/ right now.

from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class CrawledPage:
    url: str
    content_path: str
    content_type: str = "html"  # "html" | "pdf" | "docx"
    linked_from: str | None = None
    linked_from_breadcrumb: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "CrawledPage":
        return cls(
            url=d["url"],
            content_path=d.get("content_path") or d.get("path"),
            content_type=d.get("content_type") or d.get("doc_type", "html"),
            linked_from=d.get("linked_from"),
            linked_from_breadcrumb=d.get("linked_from_breadcrumb", []),
        )


@dataclass
class CleanDocument:
    doc_id: str
    url: str
    doc_type: str  # "page" | "pdf"
    title: str
    text: str
    section_path: list[str] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    source_path: str = ""
    meta: dict = field(default_factory=dict)

    def validate(self) -> None:
        if not self.doc_id or not self.url or not self.text.strip():
            raise ValueError(f"invalid CleanDocument: {self.url!r}")

    def to_dict(self) -> dict:
        return asdict(self)