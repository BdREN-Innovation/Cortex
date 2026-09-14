"""The object Team C is handed.

This is the knowledge -> evaluation seam. `VectorRetriever` implements
`contracts.retrieval.Retriever`, and that Protocol is all the evaluation team
codes against — they never import anything else from this package.

TEAM B OWNS THIS FILE.


Decisions you own
-----------------
* Do you do anything to a question before embedding it? Some systems rewrite,
  expand or strip queries first. Worth knowing about; worth measuring before
  adopting.
* Do you return everything the store gives back, or filter by score first?
  And if you filter here, how does `rag.py` still know that nothing was
  relevant?
* What does an empty or nonsense question do? Team C's dataset will contain
  edge cases, deliberately.
"""

from __future__ import annotations

import logging
from pathlib import Path

from engine.contracts.retrieval import RetrievedChunk
from engine.knowledge.embedding import Embedder, build_embedder
from engine.knowledge.store import NumpyStore, QdrantStore, load_index_meta

log = logging.getLogger(__name__)


class VectorRetriever:
    """Embed the question with the SAME embedder that built the index, then
    search. Using a different embedder at query time than at index time is the
    classic silent failure here: everything runs, and every result is noise."""

    def __init__(self, store, embedder: Embedder, index_id: str = ""):
        self.store = store
        self.embedder = embedder
        self.index_id = index_id

    def retrieve(self, question: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Return the top_k chunks as RetrievedChunk, carrying their scores and
        provenance. An empty or whitespace question returns [] rather than
        raising — Team C's dataset will contain edge cases."""
        if not question or not question.strip():
            return []

        vector = self.embedder.embed([question])[0]
        results = self.store.search(vector, top_k)
        return [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                text=chunk.text,
                score=score,
                canonical_url=chunk.canonical_url,
                title=chunk.title,
                section_path=list(chunk.section_path),
            )
            for chunk, score in results
        ]


def load_retriever(index_dir: str | Path) -> VectorRetriever:
    """Rebuild a retriever from a saved index directory.

    Read index_meta.json, reopen the store the `backend` field names (numpy or
    qdrant), and reconstruct the embedder from the recorded name and
    dimensions. This is the function that makes an index portable — get it
    right and `engine ask` works against any index anyone built.
    """
    index_dir = Path(index_dir)
    meta = load_index_meta(index_dir)
    cfg = meta.config or {}

    embedder = build_embedder(
        provider=cfg.get("embedding_provider", ""),
        model=cfg.get("embedding_model", ""),
        dimensions=meta.dimensions,
    )
    if embedder.dimensions != meta.dimensions:
        raise ValueError(
            f"{index_dir}: rebuilt embedder has {embedder.dimensions} dimensions but the "
            f"index was built with {meta.dimensions} — index_meta.json and the embedder "
            "have drifted apart"
        )

    backend = meta.backend or "numpy"
    if backend == "numpy":
        store = NumpyStore.load(index_dir)
    elif backend == "qdrant":
        store = QdrantStore(collection=meta.collection, dimensions=meta.dimensions, ensure=False)
    else:
        raise ValueError(f"{index_dir}/index_meta.json names an unknown backend: {backend!r}")

    log.info(
        "loaded index %s (%s, %s/%s)",
        meta.index_id,
        backend,
        cfg.get("embedding_provider", ""),
        embedder.name,
    )
    return VectorRetriever(store=store, embedder=embedder, index_id=meta.index_id)