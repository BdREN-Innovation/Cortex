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

from pathlib import Path

from engine.contracts.retrieval import RetrievedChunk
from engine.knowledge.embedding import Embedder


class VectorRetriever:
    """Embed the question with the SAME embedder that built the index, then
    search. Using a different embedder at query time than at index time is the
    classic silent failure here: everything runs, and every result is noise."""

    def __init__(self, store, embedder: Embedder, index_id: str = ""):
        raise NotImplementedError

    def retrieve(self, question: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Return the top_k chunks as RetrievedChunk, carrying their scores and
        provenance. An empty or whitespace question returns [] rather than
        raising — Team C's dataset will contain edge cases."""
        raise NotImplementedError


def load_retriever(index_dir: str | Path) -> VectorRetriever:
    """Rebuild a retriever from a saved index directory.

    Read index_meta.json, reopen the store the `backend` field names (numpy or
    qdrant), and reconstruct the embedder from the recorded name and
    dimensions. This is the function that makes an index portable — get it
    right and `engine ask` works against any index anyone built.
    """
    raise NotImplementedError
