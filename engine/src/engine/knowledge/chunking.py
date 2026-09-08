"""Documents -> chunks.

A chunk is the unit that gets embedded, retrieved and shown to the model. How
you cut them decides more about answer quality than almost anything else you
will choose.

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
This file has more genuinely open questions than anything else in the pipeline,
and it matters more than your embedding model. Decide these deliberately, and
be able to defend them with Team C's numbers.

* Where do you split? Sentences, paragraphs, headings, a fixed character count?
  A split mid-sentence produces a chunk that means nothing on its own.
* How big is a chunk? Too small and an answer straddles two of them so neither
  scores well; too large and the one relevant sentence is diluted.
* Do chunks overlap? By how much? Overlap catches straddling answers and costs
  you index size and embedding spend.
* Do you count tokens properly or approximate from characters? A real tokenizer
  is exact and adds a dependency; a ratio is close enough for deciding where to
  cut. Which do you actually need?
* What happens to a document shorter than one chunk? To a trailing fragment of
  four words?
* A markdown table is in the text. Splitting one down the middle produces two
  useless halves — does your splitter know that?

"""

from __future__ import annotations

from dataclasses import dataclass

from engine.contracts.documents import Chunk, CleanDocument


@dataclass
class ChunkConfig:
    """Read from `configs/index.<site>.yaml`.

    These defaults are a starting point, not an answer — they are round numbers
    somebody picked, and part of your job is to find out whether they are any
    good for your corpus. Rename or replace these fields if your chunking
    strategy wants different knobs; the config is yours.
    """

    target_tokens: int = 350
    overlap_tokens: int = 60
    min_tokens: int = 40


def chunk_document(doc: CleanDocument, config: ChunkConfig | None = None) -> list[Chunk]:
    """Split one document into chunks.

    Two things are not negotiable, because everything downstream depends on them:

    * Every chunk carries its provenance — `doc_id`, `canonical_url`, `title`,
      `section_path`. Citations are built from these. A chunk that knows its
      text but not its source is useless.
    * `chunk_id` is stable and unique across runs. Re-indexing the same corpus
      must produce the same ids, or the vector store cannot tell an update from
      a new chunk.

    Everything else — where you split, how big, whether they overlap — is the
    design work described at the top of this file.
    """
    raise NotImplementedError


def chunk_documents(docs: list[CleanDocument], config: ChunkConfig | None = None) -> list[Chunk]:
    """chunk_document over a whole corpus, flattened into one list."""
    raise NotImplementedError
