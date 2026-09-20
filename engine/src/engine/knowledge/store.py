"""Where the vectors live, and how you search them.

The project target is **Qdrant Cloud**. How you get there is yours — including
whether you build something simpler first so you are not debugging network
calls while you are still deciding on chunk size.

Three methods is the whole interface. Keep it that way and the retriever, the
RAG layer and Team C's harness never learn which backend they are talking to.

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
* Do you develop against Qdrant from day one, or against something local first?
  A network round trip per experiment is a real tax when you are sweeping chunk
  sizes. Whatever you choose, both must satisfy the same Protocol.
* What distance metric? It has to agree with whatever your embedder produces.
  If you normalise on the way in, some metrics become equivalent — know which,
  and state it explicitly rather than relying on a default.
* What is a point's ID? Re-indexing the same corpus should not double it.
  Something derived from `chunk_id` makes re-indexing idempotent; a random ID
  makes it additive. Decide deliberately.
* How much do you send per write? One enormous request will time out; one
  request per chunk will crawl.
* What does `save()` mean when the vectors are on somebody else's server?
  Something still has to be written locally, or `load_retriever` cannot find
  the collection again.
* Deleting a local index directory does not delete a remote collection. How do
  you wipe one deliberately, and how do you avoid wiping one accidentally?
* **What comes back from a search, besides the text and the score?** A citation
  has to be buildable from a search result alone — nothing downstream has
  another source to consult. Whatever a reference needs has to go into the
  store at index time and come back out at query time. See the knowledge team's
  README, "References have to live in the vector store".

Credentials come from the environment, never from a config file — `configs/` is
committed, `.env` is not.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from engine.contracts.documents import Chunk
from engine.contracts.jsonio import read_jsonl, write_jsonl, read_json, write_json

log = logging.getLogger(__name__)


class VectorStore(Protocol):
    """Three methods. Everything above this line is storage-agnostic, which is
    why changing backend changes nothing in the retriever."""

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...
    def search(self, query: np.ndarray, top_k: int) -> list[tuple[Chunk, float]]: ...
    def save(self, path: str | Path) -> None: ...


@dataclass
class IndexMeta:
    """Written as index_meta.json beside an index.

    This is how an index is reopened later, and it is shared structure: the
    retriever reads it to rebuild the right store and the right embedder. If
    something is needed to reconstruct a reader, it belongs here. Add fields as
    your design needs them.
    """

    index_id: str
    site: str
    # Must identify the embedder well enough to rebuild it. An index embedded
    # with one model and queried with another fails silently.
    embedder: str
    dimensions: int
    chunk_count: int
    doc_count: int
    built_at: str
    source_documents: str = ""
    config: dict | None = None
    # Which backend built this index, so load_retriever knows how to reopen it.
    backend: str = ""
    # Where the vectors live, when they do not live in this directory.
    collection: str = ""


# ── Your stores go here ───────────────────────────────────────────────────
#
# A class per backend, each satisfying VectorStore. Two things to be strict
# about whatever you build:
#
#   * VALIDATE on add(). len(chunks) must match vectors.shape[0], and the
#     vector width must match what the store was built for. Storing mismatched
#     data produces a search that returns the wrong chunk text — no error, just
#     wrong answers, discovered days later.
#   * search() returns (chunk, score) highest first, and returns [] for an
#     empty store rather than raising.
#
# Import client libraries lazily so a backend nobody is using need not be
# installed.


def _validate_add(chunks: list[Chunk], vectors: np.ndarray, expected_dim: int | None) -> None:
    if len(chunks) != vectors.shape[0]:
        raise ValueError(f"{len(chunks)} chunks but {vectors.shape[0]} vectors")
    if expected_dim is not None and vectors.shape[1] != expected_dim:
        raise ValueError(
            f"vector width {vectors.shape[1]} does not match store width {expected_dim}"
        )


def _point_id(chunk_id: str) -> str:
    """Deterministic point id derived from chunk_id, so re-adding the same
    chunk overwrites its old point rather than duplicating it. Qdrant only
    accepts unsigned ints or UUIDs as point ids, and `chunk_id` is neither
    (it's a 16-char hex digest), so it's mapped through uuid5 rather than
    used directly. NumpyStore doesn't need this — it keys on chunk_id as-is."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, chunk_id))


def _chunk_payload(chunk: Chunk) -> dict:
    """Everything a citation needs, stored alongside the vector. This is what
    makes a search result self-sufficient — no second file to open later."""
    return dataclasses.asdict(chunk)


def _chunk_from_payload(payload: dict) -> Chunk:
    return Chunk.from_dict(payload)


class NumpyStore:
    """A flat in-memory index, persisted as two files. No network round trip,
    no external service — the right default while chunk size and prompts are
    still moving, and completely adequate for a corpus of a few thousand
    chunks.

    Persistence, inside the index directory:
      vectors.npy   float32 matrix, one row per chunk, same order as chunks.jsonl
      chunks.jsonl  one Chunk per row — the full record, so a search result
                    alone is enough to build a citation.

    Point identity is `chunk_id` itself: adding a chunk_id that is already
    present replaces its vector and record rather than duplicating it, so
    re-indexing the same corpus is idempotent.

    Vectors are expected to already be L2-normalised (embedding.normalise()
    does this at index time and at query time), which is what lets `search`
    use a plain dot product as cosine similarity instead of a metric-specific
    codepath.
    """

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, np.ndarray] = {}
        self._dim: int | None = None

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        _validate_add(chunks, vectors, self._dim)
        self._dim = vectors.shape[1]
        for chunk, vector in zip(chunks, vectors):
            if chunk.chunk_id not in self._chunks:
                self._ids.append(chunk.chunk_id)
            self._chunks[chunk.chunk_id] = chunk
            self._vectors[chunk.chunk_id] = np.asarray(vector, dtype=np.float32)

    def search(self, query: np.ndarray, top_k: int) -> list[tuple[Chunk, float]]:
        if not self._ids:
            return []
        query = np.asarray(query, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(query)
        if norm > 0:
            query = query / norm  # defensive: the caller should already normalise
        matrix = np.stack([self._vectors[cid] for cid in self._ids])
        scores = matrix @ query
        top_k = max(0, min(top_k, len(self._ids)))
        order = np.argsort(-scores)[:top_k]
        return [(self._chunks[self._ids[i]], float(scores[i])) for i in order]

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        width = self._dim or 0
        matrix = (
            np.stack([self._vectors[cid] for cid in self._ids])
            if self._ids
            else np.zeros((0, width), dtype=np.float32)
        )
        np.save(path / "vectors.npy", matrix)
        write_jsonl(path / "chunks.jsonl", [self._chunks[cid] for cid in self._ids])

    @classmethod
    def load(cls, path: str | Path) -> "NumpyStore":
        """Reopen a store saved with `save()`. Missing files mean an empty
        (but usable) store, so a freshly-created index directory doesn't blow
        up before its first `add()`."""
        path = Path(path)
        store = cls()
        vectors_path, chunks_path = path / "vectors.npy", path / "chunks.jsonl"
        if not vectors_path.exists() or not chunks_path.exists():
            return store
        matrix = np.load(vectors_path)
        chunks = list(read_jsonl(chunks_path, factory=Chunk.from_dict))
        if matrix.shape[0] != len(chunks):
            raise ValueError(
                f"{path}: vectors.npy has {matrix.shape[0]} rows but chunks.jsonl has {len(chunks)}"
            )
        store._dim = matrix.shape[1] if matrix.size else None
        for chunk, vector in zip(chunks, matrix):
            store._ids.append(chunk.chunk_id)
            store._chunks[chunk.chunk_id] = chunk
            store._vectors[chunk.chunk_id] = vector
        return store


class QdrantStore:
    """Qdrant Cloud backend — the project target.

    Credentials come from the environment (`QDRANT_URL`, `QDRANT_API_KEY`),
    never from a config file. Distance is cosine, which agrees with the
    L2-normalised vectors `embedding.py` produces (and is correct even if a
    future embedder forgets to normalise, unlike a raw dot product).

    Every point's payload is the full `Chunk` record, so a search result is a
    complete citation on its own — nothing downstream re-opens
    documents.jsonl.

    `ensure=True` (the indexing path) creates the collection if it is missing,
    or wipes and recreates it when `recreate=True`. `ensure=False` (the
    retrieval path, via `load_retriever`) never creates or wipes anything —
    it fails loudly if the collection is gone, rather than silently opening an
    empty one.
    """

    def __init__(
        self,
        collection: str,
        dimensions: int,
        recreate: bool = False,
        ensure: bool = True,
        batch_size: int = 32,
        url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qmodels
        except ImportError as e:
            raise ImportError(
                "QdrantStore needs the qdrant-client package: run `uv add qdrant-client`"
            ) from e

        if not collection:
            raise ValueError("QdrantStore needs a collection name")

        url = url or os.environ.get("QDRANT_URL")
        api_key = api_key or os.environ.get("QDRANT_API_KEY")
        if not url:
            raise ValueError(
                "QDRANT_URL is not set. Copy engine/.env.example to engine/.env and fill it in."
            )

        self._qmodels = qmodels
        self.collection = collection
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._client = QdrantClient(url=url, api_key=api_key, timeout=120.0)

        exists = self._client.collection_exists(collection)
        if ensure:
            if recreate or not exists:
                log.info("qdrant: (re)creating collection %r (%d dims)", collection, dimensions)
                self._client.recreate_collection(
                    collection_name=collection,
                    vectors_config=qmodels.VectorParams(
                        size=dimensions, distance=qmodels.Distance.COSINE
                    ),
                )
        elif not exists:
            raise ValueError(
                f"Qdrant collection {collection!r} does not exist yet — build the index first"
            )

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        _validate_add(chunks, vectors, self.dimensions)
        points = [
            self._qmodels.PointStruct(
                id=_point_id(chunk.chunk_id),
                vector=np.asarray(vector, dtype=np.float32).tolist(),
                payload=_chunk_payload(chunk),
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        for start in range(0, len(points), self.batch_size):
            batch = points[start : start + self.batch_size]
            self._client.upsert(collection_name=self.collection, points=batch, wait=True)
        log.info("qdrant: upserted %d point(s) into %r", len(points), self.collection)

    def search(self, query: np.ndarray, top_k: int) -> list[tuple[Chunk, float]]:
        query = np.asarray(query, dtype=np.float32).reshape(-1)
        result = self._client.query_points(
            collection_name=self.collection,
            query=query.tolist(),
            limit=top_k,
            with_payload=True,
        )
        return [(_chunk_from_payload(point.payload), float(point.score)) for point in result.points]

    def save(self, path: str | Path) -> None:
        """The vectors already live on Qdrant Cloud — nothing to persist
        there. What's written locally is just enough for `load_retriever` to
        find the same collection again without re-reading documents.jsonl."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        write_json(
            path / "qdrant.json", {"collection": self.collection, "dimensions": self.dimensions}
        )


def build_store(
    backend: str,
    dimensions: int,
    collection: str = "",
    recreate: bool = False,
    ensure: bool = True,
) -> "NumpyStore | QdrantStore":
    """Map the `backend:` string in an index config to one of the stores
    above. Defaults to `numpy` so a fresh clone can index and ask against the
    fixture site with no external service and no keys."""
    backend = backend or "numpy"
    if backend == "numpy":
        return NumpyStore()
    if backend == "qdrant":
        return QdrantStore(
            collection=collection, dimensions=dimensions, recreate=recreate, ensure=ensure
        )
    raise ValueError(f"Unknown backend: {backend!r}. Supported: 'numpy', 'qdrant'.")


def save_index_meta(path: str | Path, meta: IndexMeta) -> None:
    """Write index_meta.json into the index directory."""
    write_json(Path(path) / "index_meta.json", dataclasses.asdict(meta))


def load_index_meta(path: str | Path) -> IndexMeta:
    """Read it back."""
    payload = read_json(Path(path) / "index_meta.json")
    return IndexMeta(**payload)