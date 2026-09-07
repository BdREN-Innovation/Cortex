"""documents.jsonl -> a searchable index.

Chains chunking, embedding and storage, then writes index_meta.json so the
index can be reopened later. Build this after those three work.

TEAM B OWNS THIS FILE.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from engine.knowledge.chunking import ChunkConfig

log = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """Read from `configs/index.<site>.yaml`."""

    site: str = "default"
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    dimensions: int = 1536
    # "numpy" (offline, exact, what CI uses) or "qdrant" (Qdrant Cloud).
    backend: str = "numpy"
    # Qdrant only. Defaults to cortex_<site>. Credentials come from the
    # environment — never put an API key in a committed config.
    collection: str = ""
    recreate_collection: bool = False
    chunk: ChunkConfig = field(default_factory=ChunkConfig)

    @classmethod
    def from_dict(cls, payload: dict) -> "IndexConfig":
        """The nested `chunk:` block becomes a ChunkConfig."""
        raise NotImplementedError


def build_index(
    documents_path: str | Path,
    out_root: str | Path = "data",
    config: IndexConfig | None = None,
    index_id: str | None = None,
) -> Path:
    """Read documents.jsonl, chunk, embed, store. Returns the index directory.

    Steps:
      1. Read the documents. Refuse an empty file with a clear error.
      2. VALIDATE every row with CleanDocument.validate() and refuse the whole
         file if any row fails, naming the first few offenders. A bad row that
         reaches the index produces a broken citation much later, where nobody
         can trace it back here.
      3. Chunk, then embed all chunk texts.
      4. Build the store the config asks for and add everything.
      5. Write to `<out_root>/index/<site>/<index_id>/` and save an IndexMeta
         recording the embedder, dimensions, counts, backend and collection.

    Derive `index_id` from the inputs that change results (documents path,
    embedder name, chunk size) so re-running with the same settings lands in the
    same directory, and changing a setting gives you a new one to compare.
    """
    raise NotImplementedError
