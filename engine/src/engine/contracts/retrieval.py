"""The knowledge -> evaluation handoff.

The eval team codes against `Retriever` only. That is what lets them build and
run the whole harness against a stub while the real RAG stack is still being
written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    text: str
    score: float
    canonical_url: str = ""
    title: str = ""
    section_path: list[str] = field(default_factory=list)


@runtime_checkable
class Retriever(Protocol):
    """Anything that can turn a question into ranked chunks."""

    def retrieve(self, question: str, top_k: int = 5) -> list[RetrievedChunk]: ...
