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

Credentials come from the environment, never from a config file — `configs/` is
committed, `.env` is not.
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


def save_index_meta(path: str | Path, meta: IndexMeta) -> None:
    """Write index_meta.json into the index directory."""
    raise NotImplementedError


def load_index_meta(path: str | Path) -> IndexMeta:
    """Read it back."""
    raise NotImplementedError
