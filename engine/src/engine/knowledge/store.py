"""Vector storage behind one interface.

Two implementations. `NumpyVectorStore` is brute-force cosine over a matrix —
that sounds primitive, but at this corpus size it is exact, dependency-free and
fast enough to be invisible next to an LLM call. `QdrantVectorStore` is the
production path.

Build NumPy first and develop against it. Switch to Qdrant when you are
integrating, not while you are still iterating on chunk size — a network round
trip per experiment will slow you down for no benefit at 800 chunks.

TEAM B OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

numpy           the matrix, np.save/np.load, and argpartition for top-k
                without sorting the whole array.
qdrant-client   `uv add qdrant-client`. QdrantClient(url, api_key),
                create_collection, upsert(PointStruct), query_points.
uuid            uuid5 to derive stable point IDs from chunk_ids.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from engine.contracts.documents import Chunk

log = logging.getLogger(__name__)


class VectorStore(Protocol):
    """Three methods. Everything above this line is storage-agnostic, which is
    why swapping NumPy for Qdrant changes nothing in the retriever."""

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...
    def search(self, query: np.ndarray, top_k: int) -> list[tuple[Chunk, float]]: ...
    def save(self, path: str | Path) -> None: ...


@dataclass
class IndexMeta:
    """Written as index_meta.json beside an index. This is how an index is
    reopened later, so it must record everything needed to rebuild the reader."""

    index_id: str
    site: str
    embedder: str
    dimensions: int
    chunk_count: int
    doc_count: int
    built_at: str
    source_documents: str = ""
    config: dict | None = None
    # "numpy" or "qdrant". load_retriever() reads this to decide how to rebuild
    # the store, so an index built against Qdrant Cloud reopens against it.
    backend: str = "numpy"
    # Qdrant only: the collection the vectors live in. The server URL and key
    # come from the environment, never from a committed file.
    collection: str = ""


class NumpyVectorStore:
    """Exact cosine search over a matrix in memory.

    Vectors arrive already L2-normalised from the embedder, so a dot product
    IS the cosine similarity and `search` is one matrix multiply.
    """

    def __init__(self, dimensions: int):
        raise NotImplementedError

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        """Append. Validate loudly: len(chunks) must equal vectors.shape[0],
        and vectors.shape[1] must equal self.dimensions. Silently storing
        mismatched data produces a search that returns the wrong chunk text,
        which is very hard to debug later."""
        raise NotImplementedError

    def search(self, query: np.ndarray, top_k: int = 5) -> list[tuple[Chunk, float]]:
        """Top-k by cosine, highest first. Return [] for an empty store rather
        than raising. np.argpartition finds the top k without sorting the whole
        array — worth using once the corpus is real."""
        raise NotImplementedError

    def save(self, path: str | Path) -> None:
        """Persist to a directory: vectors.npy plus chunks.jsonl. Keep the two
        in the same order — that ordering is the only thing linking a row of
        the matrix to its chunk."""
        raise NotImplementedError

    @classmethod
    def load(cls, path: str | Path) -> "NumpyVectorStore":
        """The inverse of save. Round-tripping must preserve search results."""
        raise NotImplementedError


class QdrantVectorStore:
    """Qdrant Cloud, behind the same three methods.

    Credentials come from QDRANT_URL and QDRANT_API_KEY in engine/.env. Never
    put a key in a config file: configs/ is committed, .env is not.

    Four things worth getting right:
      * Derive each point ID from `chunk_id` (uuid5 over the chunk_id) so
        re-indexing REPLACES a chunk instead of duplicating it.
      * Batch upserts (~256 points). One upsert of 50k points is a timeout.
      * `save()` writes nothing — the vectors live on the server. index_meta
        records the collection name, and that is enough to reopen it.
      * Deleting data/index/ does NOT delete the collection. Offer a
        `recreate` flag for wiping it deliberately.
    """

    def __init__(
        self,
        collection: str,
        dimensions: int,
        url: str = "",
        api_key: str = "",
        recreate: bool = False,
    ):
        raise NotImplementedError

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        raise NotImplementedError

    def search(self, query: np.ndarray, top_k: int = 5) -> list[tuple[Chunk, float]]:
        """Store the whole chunk in the point payload, so a hit can be turned
        back into a Chunk without a second lookup somewhere else."""
        raise NotImplementedError

    def save(self, path: str | Path) -> None:
        raise NotImplementedError

    @classmethod
    def load(cls, path: str | Path) -> "QdrantVectorStore":
        raise NotImplementedError


def save_index_meta(path: str | Path, meta: IndexMeta) -> None:
    """Write index_meta.json into the index directory."""
    raise NotImplementedError


def load_index_meta(path: str | Path) -> IndexMeta:
    """Read it back."""
    raise NotImplementedError
