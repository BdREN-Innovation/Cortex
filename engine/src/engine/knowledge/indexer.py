"""Build an index directory from a documents.jsonl produced by the crawler."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from engine.contracts.documents import CleanDocument
from engine.contracts.jsonio import read_jsonl
from engine.knowledge.chunking import ChunkConfig, chunk_documents
from engine.knowledge.embedding import build_embedder
from engine.knowledge.store import IndexMeta, NumpyVectorStore, save_index_meta

log = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    site: str = "default"
    embedding_provider: str = "hash"
    embedding_model: str = ""
    dimensions: int = 512
    chunk: ChunkConfig = field(default_factory=ChunkConfig)

    @classmethod
    def from_dict(cls, payload: dict) -> "IndexConfig":
        chunk = ChunkConfig(**payload.get("chunk", {}))
        known = {f for f in cls.__dataclass_fields__ if f != "chunk"}
        return cls(chunk=chunk, **{k: v for k, v in payload.items() if k in known})


def build_index(
    documents_path: str | Path,
    out_root: str | Path = "data",
    config: IndexConfig | None = None,
    index_id: str | None = None,
) -> Path:
    config = config or IndexConfig()
    documents_path = Path(documents_path)

    docs = [CleanDocument.from_dict(row) for row in read_jsonl(documents_path)]
    if not docs:
        raise ValueError(f"{documents_path} contains no documents")

    invalid = [(d.doc_id, problems) for d in docs if (problems := d.validate())]
    if invalid:
        for doc_id, problems in invalid[:5]:
            log.warning("document %s failed validation: %s", doc_id, "; ".join(problems))
        raise ValueError(
            f"{len(invalid)} document(s) violate the CleanDocument contract; "
            "the crawler must fix these before indexing"
        )

    chunks = chunk_documents(docs, config.chunk)
    if not chunks:
        raise ValueError("chunking produced nothing — check chunk sizes against document length")

    embedder = build_embedder(config.embedding_provider, config.embedding_model, config.dimensions)
    log.info("embedding %s chunks from %s documents with %s", len(chunks), len(docs), embedder.name)
    vectors = embedder.embed([c.text for c in chunks])

    store = NumpyVectorStore(dimensions=vectors.shape[1])
    store.add(chunks, vectors)

    index_id = index_id or hashlib.sha256(
        f"{documents_path}|{embedder.name}|{config.chunk.target_tokens}".encode()
    ).hexdigest()[:12]

    index_dir = Path(out_root) / "index" / config.site / index_id
    store.save(index_dir)
    save_index_meta(
        index_dir,
        IndexMeta(
            index_id=index_id,
            site=config.site,
            embedder=f"{config.embedding_provider}:{config.embedding_model}".rstrip(":"),
            dimensions=int(vectors.shape[1]),
            chunk_count=len(chunks),
            doc_count=len(docs),
            built_at=datetime.now(timezone.utc).isoformat(),
            source_documents=str(documents_path),
            config={
                "target_tokens": config.chunk.target_tokens,
                "overlap_tokens": config.chunk.overlap_tokens,
            },
        ),
    )
    log.info("index %s built -> %s", index_id, index_dir)
    return index_dir
