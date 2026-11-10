"""documents.jsonl -> a searchable index.

Chains chunking, embedding and storage, then writes index_meta.json so the
index can be reopened later. Build this after those three work.

TEAM B OWNS THIS FILE.


Decisions you own
-----------------
* What identifies an index? It should change when something that changes
  results changes, so two settings produce two indexes you can compare — and
  re-running the same settings lands in the same place rather than duplicating.
* How strict are you about bad input? A malformed document that reaches the
  index produces a broken citation much later, somewhere nobody can trace back
  to here.
* What has to be recorded for `load_retriever` to reopen this index later?
  Whatever the answer is, it belongs in IndexMeta.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from engine.contracts.documents import CleanDocument
from engine.contracts.jsonio import read_jsonl
from engine.knowledge.chunking import ChunkConfig, chunk_documents
from engine.knowledge.embedding import build_embedder
from engine.knowledge.store import IndexMeta, build_store, save_index_meta

log = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """Read from `configs/index.<site>.yaml`."""

    site: str = "default"
    # Names one of the embedders you register in embedding.py.
    embedding_provider: str = ""
    embedding_model: str = ""
    dimensions: int = 0
    # Names one of the stores you register in store.py.
    backend: str = ""
    # Where the vectors live, when they live on a server. Credentials come
    # from the environment — never put an API key in a committed config.
    collection: str = ""
    recreate_collection: bool = False
    chunk: ChunkConfig = field(default_factory=ChunkConfig)

    @classmethod
    def from_dict(cls, payload: dict) -> "IndexConfig":
        """The nested `chunk:` block becomes a ChunkConfig."""
        chunk_payload = payload.get("chunk") or {}
        chunk_config = ChunkConfig(
            target_tokens=chunk_payload.get("target_tokens", 350),
            overlap_tokens=chunk_payload.get("overlap_tokens", 60),
            min_tokens=chunk_payload.get("min_tokens", 40),
        )
        return cls(
            site=payload.get("site", "default"),
            embedding_provider=payload.get("embedding_provider", ""),
            embedding_model=payload.get("embedding_model", ""),
            dimensions=payload.get("dimensions", 0),
            backend=payload.get("backend", ""),
            collection=payload.get("collection", ""),
            recreate_collection=payload.get("recreate_collection", False),
            chunk=chunk_config,
        )


def _default_index_id(config: IndexConfig, documents_path: str | Path) -> str:
    """Derived only from settings that change results — embedder, chunking,
    backend/collection — plus the input file. Same settings + same input land
    in the same directory (re-running is a no-op rebuild, not a duplicate);
    changing any of them produces a new id to compare against the old one."""
    fingerprint = {
        "site": config.site,
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "backend": config.backend,
        "collection": config.collection,
        "chunk": asdict(config.chunk),
        "documents_path": str(Path(documents_path).resolve()),
    }
    payload = json.dumps(fingerprint, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def build_index(
    documents_path: str | Path,
    out_root: str | Path = "data",
    config: IndexConfig | None = None,
    index_id: str | None = None,
) -> Path:
    """Read documents.jsonl, chunk, embed, store. Returns the index directory.

    Chains chunking, embedding and storage, then records enough in
    `index_meta.json` that `load_retriever` can reopen what you built.

    Two things worth being strict about:

      * Validate every row before indexing and refuse the whole file if any
        fails. A bad row that reaches the index produces a broken citation much
        later, somewhere nobody can trace back to here.
      * `index_id` should be derived from the inputs that change results, so
        re-running with the same settings lands in the same place and changing
        a setting gives you a new index to compare against the old one.
    """
    config = config or IndexConfig()
    documents_path = Path(documents_path)

    docs = list(read_jsonl(documents_path, factory=CleanDocument.from_dict))
    if not docs:
        raise ValueError(f"No documents found in {documents_path}")

    problems = []
    for doc in docs:
        problems.extend(f"{doc.doc_id or '<no id>'}: {p}" for p in doc.validate())
    if problems:
        preview = "\n  ".join(problems[:10])
        raise ValueError(
            f"{len(problems)} invalid document(s) in {documents_path}, refusing to index:\n  {preview}"
        )

    chunks = chunk_documents(docs, config.chunk)
    if not chunks:
        raise ValueError(f"Chunking produced zero chunks from {len(docs)} document(s)")

    embedder = build_embedder(
        provider=config.embedding_provider,
        model=config.embedding_model,
        dimensions=config.dimensions,
    )
    vectors = embedder.embed([chunk.text for chunk in chunks])

    resolved_id = index_id or _default_index_id(config, documents_path)
    index_dir = Path(out_root) / "index" / config.site / resolved_id
    index_dir.mkdir(parents=True, exist_ok=True)

    backend = config.backend or "numpy"
    store = build_store(
        backend=backend,
        dimensions=embedder.dimensions,
        collection=config.collection,
        recreate=config.recreate_collection,
        ensure=True,
    )
    store.add(chunks, vectors)
    store.save(index_dir)

    meta = IndexMeta(
        index_id=resolved_id,
        site=config.site,
        embedder=embedder.name,
        dimensions=embedder.dimensions,
        chunk_count=len(chunks),
        doc_count=len(docs),
        built_at=datetime.now(timezone.utc).isoformat(),
        source_documents=str(documents_path),
        config=asdict(config),
        backend=backend,
        collection=config.collection,
    )
    save_index_meta(index_dir, meta)

    log.info(
        "built index %s (%s): %d document(s) -> %d chunk(s), embedder=%s/%s, backend=%s",
        resolved_id,
        config.site,
        len(docs),
        len(chunks),
        config.embedding_provider,
        embedder.name,
        backend,
    )
    return index_dir