"""Documents -> chunks.

The highest-leverage knob in the whole system. `target_tokens` matters more
than your choice of embedding model: too small and an answer straddles two
chunks so neither scores well; too large and the one relevant sentence is
diluted by 300 tokens of neighbours. Sweep it once Team C has a dataset.

TEAM B OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

Nothing required — splitting on paragraphs with a character budget is ~60 lines
and easy to reason about. A rough chars-per-token ratio (~4) is fine; you do not
need a real tokenizer to decide where to cut.

Worth knowing about, and worth resisting until the simple version is measured:
  tiktoken                  real token counts for OpenAI models
  langchain-text-splitters  RecursiveCharacterTextSplitter, the usual default
  semchunk                  semantic chunking
A hand-written paragraph splitter that you understand will beat a library you
cannot debug at 2am on day 12.

"""

from __future__ import annotations

from dataclasses import dataclass

from engine.contracts.documents import Chunk, CleanDocument


@dataclass
class ChunkConfig:
    target_tokens: int = 350
    overlap_tokens: int = 60
    min_tokens: int = 40

    # Token budgets are expressed in tokens because that is how models think,
    # but splitting happens on characters. ~4 chars per token is close enough.
    @property
    def target_chars(self) -> int:
        raise NotImplementedError

    @property
    def overlap_chars(self) -> int:
        raise NotImplementedError

    @property
    def min_chars(self) -> int:
        raise NotImplementedError


def chunk_document(doc: CleanDocument, config: ChunkConfig | None = None) -> list[Chunk]:
    """Split one document into overlapping chunks.

    Split on paragraph boundaries, not mid-sentence: accumulate paragraphs
    until adding the next would exceed `target_chars`, emit, then start the
    next chunk with `overlap_chars` of tail from the previous one. The overlap
    is what catches an answer that straddles a boundary.

    Every chunk must carry its provenance — `doc_id`, `canonical_url`, `title`,
    `section_path` — because that is what citations are built from downstream.
    A chunk that knows its text but not its source is useless.

    `chunk_id` must be stable and unique: derive it from doc_id plus ordinal.

    Two edge cases that must be handled:
      * A document shorter than one chunk produces exactly ONE chunk, not zero.
      * A trailing fragment below `min_chars` should not become its own chunk —
        fold it into the previous one instead of emitting a stub.
    """
    raise NotImplementedError


def chunk_documents(docs: list[CleanDocument], config: ChunkConfig | None = None) -> list[Chunk]:
    """chunk_document over a whole corpus, flattened into one list."""
    raise NotImplementedError
