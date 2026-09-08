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

import logging
from dataclasses import dataclass, field
from pathlib import Path

from engine.knowledge.chunking import ChunkConfig

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
        raise NotImplementedError


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
    raise NotImplementedError
