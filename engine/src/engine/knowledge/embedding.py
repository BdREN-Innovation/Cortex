"""Text -> vectors.

Embeddings come from a hosted API — that is a project decision, so nothing runs
a model on your laptop. Beyond that, which provider and which model are yours to
choose.

The Protocol is the structure: `dimensions`, `name`, and `embed()`. Everything
downstream depends only on those three, which is what lets you change your mind
about providers without touching the indexer or the retriever.

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
* Which provider? Several offer embeddings endpoints and they are all the same
  shape — a batch of strings in, a list of float arrays out. Price, dimensions
  and quality differ. Compare at least two before committing.
* Which model, within that provider? Bigger vectors are usually better and
  always cost more, in money and in index size. Is the difference visible in
  Team C's scores? That is the only question that matters.
* How many strings per request? One call per chunk is slow and expensive; too
  many and you hit a request-size limit.
* What happens when the API rate-limits you, or times out, halfway through a
  10,000-chunk run? Losing forty minutes of work to one 429 is avoidable, but
  only if you plan for it.
* Should identical text be re-embedded every time you re-index? `content_hash`
  is on every document. Whether you use it to avoid paying twice is up to you —
  and it matters most while you are sweeping chunk sizes.

One thing that is not a choice
------------------------------
Whatever produces the vectors at index time must also produce them at query
time. `index_meta.json` records `name` for exactly this reason. Embedding a
corpus with one model and querying it with another returns confident nonsense
and no error — the nastiest failure mode in this pipeline.

One thing to check early, before you plan around a provider: not every company
offering an LLM API also offers an embeddings endpoint. Some are generation
only. Confirm it exists before you build against it.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class Embedder(Protocol):
    """What the indexer and the retriever depend on. Nothing above this line
    knows which provider produced the numbers."""

    # Length of the vectors this embedder returns. Goes into index_meta.json.
    dimensions: int
    # Identifies the model well enough to rebuild this embedder later.
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def normalise(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise each row, so a dot product IS the cosine similarity.

    Doing it once here means the vector store never has to.

    Watch the zero-length row: dividing by zero produces NaNs that then poison
    every search result silently. It is a nasty bug to track down after the fact.
    """
    raise NotImplementedError


# ── Your embedders go here ────────────────────────────────────────────────
#
# A class per provider you want to be able to switch between. Each needs
# `dimensions`, `name`, and `embed(texts) -> np.ndarray` returning one
# normalised row per input string, IN THE SAME ORDER as the input — the caller
# zips this against its chunk list, so a reordered response quietly attaches
# every vector to the wrong text.
#
# Import the client library lazily and fail with a message that names the
# `uv add` and the environment variable needed.


def build_embedder(provider: str = "", model: str = "", dimensions: int = 0) -> Embedder:
    """Map the `embedding_provider:` string in an index config to one of yours.

    Raise ValueError for an unknown provider, naming what IS supported.
    """
    raise NotImplementedError
