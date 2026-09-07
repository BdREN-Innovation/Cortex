"""Vector store behind one interface.

The default implementation is brute-force cosine over a NumPy matrix. That
sounds primitive, but at these corpus sizes (tens of thousands of chunks) it is
exact, dependency-free and fast enough to be invisible next to an LLM call.

When the corpus outgrows it, add a pgvector implementation of the same three
methods — the retriever and everything above it will not change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from engine.contracts.documents import Chunk
from engine.contracts.jsonio import read_json, write_json


class VectorStore(Protocol):
    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...
    def search(self, query: np.ndarray, top_k: int) -> list[tuple[Chunk, float]]: ...
    def save(self, path: str | Path) -> None: ...


@dataclass
class IndexMeta:
    index_id: str
    site: str
    embedder: str
    dimensions: int
    chunk_count: int
    doc_count: int
    built_at: str
    source_documents: str = ""
    config: dict | None = None


class NumpyVectorStore:
    """Exact cosine search. Vectors are L2-normalised on the way in, so a dot
    product is the cosine similarity."""

    def __init__(self, dimensions: int):
        self.dimensions = dimensions
        self.chunks: list[Chunk] = []
        self._vectors: np.ndarray = np.zeros((0, dimensions), dtype=np.float32)

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        if len(chunks) != vectors.shape[0]:
            raise ValueError(f"{len(chunks)} chunks but {vectors.shape[0]} vectors")
        if vectors.shape[1] != self.dimensions:
            raise ValueError(f"expected {self.dimensions}-d vectors, got {vectors.shape[1]}")
        self.chunks.extend(chunks)
        self._vectors = np.vstack([self._vectors, vectors.astype(np.float32)])

    def search(self, query: np.ndarray, top_k: int = 5) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        scores = self._vectors @ query.reshape(-1)
        top_k = min(top_k, len(self.chunks))
        # argpartition finds the top-k without sorting the whole array.
        candidates = np.argpartition(-scores, top_k - 1)[:top_k]
        ordered = candidates[np.argsort(-scores[candidates])]
        return [(self.chunks[i], float(scores[i])) for i in ordered]

    # -- persistence --------------------------------------------------------
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        np.save(path / "vectors.npy", self._vectors)
        with (path / "chunks.jsonl").open("w", encoding="utf-8") as handle:
            for chunk in self.chunks:
                handle.write(json.dumps(chunk.__dict__, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "NumpyVectorStore":
        path = Path(path)
        vectors = np.load(path / "vectors.npy")
        store = cls(dimensions=int(vectors.shape[1]) if vectors.size else 0)
        store._vectors = vectors
        with (path / "chunks.jsonl").open(encoding="utf-8") as handle:
            store.chunks = [Chunk.from_dict(json.loads(line)) for line in handle if line.strip()]
        return store


def save_index_meta(path: str | Path, meta: IndexMeta) -> None:
    write_json(Path(path) / "index_meta.json", meta)


def load_index_meta(path: str | Path) -> IndexMeta:
    return IndexMeta(**read_json(Path(path) / "index_meta.json"))
