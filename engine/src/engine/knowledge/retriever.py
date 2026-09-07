"""The object the evaluation team is handed. Implements contracts.retrieval.Retriever."""

from __future__ import annotations

from pathlib import Path

from engine.contracts.retrieval import RetrievedChunk
from engine.knowledge.embedding import Embedder, build_embedder
from engine.knowledge.store import NumpyVectorStore, load_index_meta


class VectorRetriever:
    def __init__(self, store: NumpyVectorStore, embedder: Embedder, index_id: str = ""):
        self.store = store
        self.embedder = embedder
        self.index_id = index_id

    def retrieve(self, question: str, top_k: int = 5) -> list[RetrievedChunk]:
        if not question.strip():
            return []
        query = self.embedder.embed([question])[0]
        return [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                text=chunk.text,
                score=score,
                canonical_url=chunk.canonical_url,
                title=chunk.title,
                section_path=chunk.section_path,
            )
            for chunk, score in self.store.search(query, top_k=top_k)
        ]


def load_retriever(index_dir: str | Path) -> VectorRetriever:
    """Rebuild a retriever from a saved index directory."""
    index_dir = Path(index_dir)
    meta = load_index_meta(index_dir)
    store = NumpyVectorStore.load(index_dir)

    provider, _, model = meta.embedder.partition(":")
    embedder = build_embedder(
        provider=provider,
        model=model,
        dimensions=meta.dimensions,
    )
    return VectorRetriever(store=store, embedder=embedder, index_id=meta.index_id)
