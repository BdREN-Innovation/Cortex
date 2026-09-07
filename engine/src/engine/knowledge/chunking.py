"""CleanDocument -> Chunk[].

Chunking is the single highest-leverage knob in a RAG system, so it is kept
deliberately simple and configurable: split on paragraph boundaries, pack up to
a target size, and overlap a little so an answer straddling a boundary is not
lost.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from engine.contracts.documents import Chunk, CleanDocument

# ~4 characters per token is a rough but stable heuristic across English prose.
CHARS_PER_TOKEN = 4


@dataclass
class ChunkConfig:
    target_tokens: int = 350
    overlap_tokens: int = 60
    min_tokens: int = 40

    @property
    def target_chars(self) -> int:
        return self.target_tokens * CHARS_PER_TOKEN

    @property
    def overlap_chars(self) -> int:
        return self.overlap_tokens * CHARS_PER_TOKEN

    @property
    def min_chars(self) -> int:
        return self.min_tokens * CHARS_PER_TOKEN


def _paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n{2,}", text)
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # A single paragraph longer than any window gets split on sentences.
        if len(part) > 4000:
            out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", part) if s.strip())
        else:
            out.append(part)
    return out


def chunk_document(doc: CleanDocument, config: ChunkConfig | None = None) -> list[Chunk]:
    config = config or ChunkConfig()
    paragraphs = _paragraphs(doc.text)
    if not paragraphs:
        return []

    windows: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= config.target_chars or not current:
            current = candidate
        else:
            windows.append(current)
            tail = current[-config.overlap_chars:] if config.overlap_chars else ""
            current = f"{tail}\n\n{paragraph}" if tail else paragraph
    if current:
        windows.append(current)

    # Fold a too-small trailing window back into its predecessor rather than
    # emitting a fragment that will never retrieve well.
    if len(windows) > 1 and len(windows[-1]) < config.min_chars:
        windows[-2] = f"{windows[-2]}\n\n{windows[-1]}"
        windows.pop()

    chunks = []
    for ordinal, window in enumerate(windows):
        raw_id = f"{doc.doc_id}:{ordinal}"
        chunks.append(
            Chunk(
                chunk_id=hashlib.sha256(raw_id.encode()).hexdigest()[:16],
                doc_id=doc.doc_id,
                text=window,
                ordinal=ordinal,
                canonical_url=doc.canonical_url,
                title=doc.title,
                section_path=doc.section_path,
                token_estimate=len(window) // CHARS_PER_TOKEN,
                meta={"lang": doc.lang},
            )
        )
    return chunks


def chunk_documents(docs: list[CleanDocument], config: ChunkConfig | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        chunks.extend(chunk_document(doc, config))
    return chunks
