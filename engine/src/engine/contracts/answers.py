"""The shape of a generated answer. Citations are mandatory, not decorative:
the evaluation team grades them, so an answer without them scores zero."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Citation:
    doc_id: str
    chunk_id: str
    canonical_url: str
    title: str = ""
    section_path: list[str] = field(default_factory=list)
    quote: str = ""


@dataclass
class Answer:
    question: str
    text: str
    citations: list[Citation] = field(default_factory=list)
    # True when the system correctly declines because the context does not
    # support an answer. Refusing well is a feature and is scored as one.
    refused: bool = False
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    latency_ms: int = 0
    usage: dict = field(default_factory=dict)
