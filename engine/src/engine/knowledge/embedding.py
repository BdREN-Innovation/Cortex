"""Text -> vectors, via an embeddings API.

Embeddings come from a hosted API. Nothing runs a model on your laptop: no
torch, no model weights, no GPU. You send a batch of strings over HTTPS and get
back a list of float arrays.

Note for the team: **Anthropic does not ship an embeddings endpoint.** It is a
*generation* provider only. Someone will try it; the error message in
`build_embedder` is there to save them the afternoon.

TEAM B OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

openai    `uv add openai`. The client is two calls:
              from openai import OpenAI
              client = OpenAI()                      # reads OPENAI_API_KEY
              client.embeddings.create(model=..., input=[...])
          `text-embedding-3-small` is 1536 dimensions and cheap;
          `text-embedding-3-large` is 3072 and better. Start small.
numpy     assembling the response into a matrix, and normalising it.

Other hosted options, if you want to compare: Cohere (`cohere`), Voyage AI
(`voyageai`), Jina. All the same shape — batch of strings in, vectors out — so
adding one is another class implementing the same three attributes.

Things to get right
-------------------
* BATCH. The endpoint takes a list. One request per chunk is slow and
  expensive; ~128 per request keeps bodies sane.
* NORMALISE on the way in, so a dot product is the cosine similarity and the
  vector store never has to care.
* HANDLE FAILURE. Rate limits (429) and transient 5xx will happen on a real
  corpus. Retry with backoff; do not lose a 40-minute indexing run to one
  blip.
* COST is real. Embedding 10,000 chunks is cheap but not free, and re-indexing
  the same corpus ten times while tuning `target_tokens` costs ten times as
  much. Cache by `content_hash` if you find yourself re-running a lot.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)

# Sent with every batch. Keep it well under the provider's request-size limit.
BATCH_SIZE = 128


class Embedder(Protocol):
    """What the indexer and the retriever depend on. Nothing above this line
    knows which provider produced the numbers."""

    dimensions: int
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def normalise(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise each row, so a dot product IS the cosine similarity.

    Doing it once here means the vector store never has to. Guard against a
    zero-length row — dividing by zero silently produces NaNs that then poison
    every search result, and it is a genuinely nasty bug to track down.
    """
    raise NotImplementedError


class OpenAIEmbedder:
    """Embeddings from the OpenAI API.

    Requires OPENAI_API_KEY in engine/.env and `uv add openai`.
    """

    def __init__(self, model: str = "text-embedding-3-small", dimensions: int = 1536):
        """Import `openai` lazily and fail with a clear, actionable message if
        the extra is not installed or the key is not set.

        Set `self.name` to something that identifies the model, because it goes
        into `index_meta.json` and is what `load_retriever` uses to rebuild the
        right embedder later. An index embedded with one model and queried with
        another returns confident nonsense.
        """
        raise NotImplementedError

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (len(texts), dimensions) float32 array, L2-normalised.

        Send `texts` in batches of BATCH_SIZE. Keep the results in the SAME
        ORDER as the input — the caller zips this array against its chunk list,
        so a reordered response silently attaches every vector to the wrong text.

        Retry on 429 and 5xx with backoff.
        """
        raise NotImplementedError


def build_embedder(provider: str = "openai", model: str = "", dimensions: int = 1536) -> Embedder:
    """Map a config string to an embedder.

    "openai" is the supported provider today. Add others here as you try them.

    "anthropic" must raise a ValueError that SAYS WHY — Anthropic has no
    embeddings API, and a bare KeyError three frames down would waste real time.
    """
    raise NotImplementedError
