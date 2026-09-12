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

Text -> vectors.

Embeddings come from a hosted API — that is a project decision, so nothing runs
a model on your laptop. Beyond that, which provider and which model are yours to
choose.

The Protocol is the structure: `dimensions`, `name`, and `embed()`. Everything
downstream depends only on those three, which is what lets you change your mind
about providers without touching the indexer or the retriever.

TEAM B OWNS THIS FILE.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

from dotenv import load_dotenv
load_dotenv()

import numpy as np

log = logging.getLogger(__name__)


class Embedder(Protocol):
    """What the indexer and the retriever depend on. Nothing above this line
    knows which provider produced the numbers."""

    dimensions: int
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def normalise(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise each row, so a dot product IS the cosine similarity.

    Doing it once here means the vector store never has to.

    Watch the zero-length row: dividing by zero produces NaNs that then poison
    every search result silently. Guard it explicitly rather than hoping every
    provider always returns a non-zero vector for every input.
    """
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    zero_rows = (norms.squeeze(-1) == 0)
    if zero_rows.any():
        log.warning("normalise: %d zero-length vector(s) — leaving them as zeros, not dividing", zero_rows.sum())
        norms[zero_rows] = 1.0  # avoid div-by-zero; row stays all-zero, not NaN
    return matrix / norms


def _embed_with_retry(call, batch: list[str], max_retries: int, provider_label: str) -> list[list[float]]:
    """Shared retry/backoff wrapper for a provider's raw API call.

    `call(batch)` should return the raw list of embedding vectors for that
    batch. Retries on any exception (rate limits, timeouts, transient network
    errors all surface as exceptions from these SDKs) with exponential
    backoff, so one 429 mid-run doesn't lose the whole batch's work.
    """
    delay = 1.0
    for attempt in range(max_retries):
        try:
            return call(batch)
        except Exception as e:
            if attempt == max_retries - 1:
                log.error("%s embed batch failed after %d attempts: %s", provider_label, max_retries, e)
                raise
            log.warning(
                "%s embed batch failed (attempt %d/%d): %s — retrying in %.1fs",
                provider_label, attempt + 1, max_retries, e, delay,
            )
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")  # loop always returns or raises


# ── Provider embedders ────────────────────────────────────────────────────
#
# Each returns one row per input string, IN THE SAME ORDER as the input — every
# provider below preserves input order in its batch response, so zipping the
# result against the chunk list is safe. Verify this assumption for any new
# provider you add; it's not guaranteed by the interface, just true so far.


class OpenAIEmbedder:
    """OpenAI's embeddings endpoint.

    Needs: `uv add openai`, and `OPENAI_API_KEY` set in the environment.
    Not multilingual-specialized, but text-embedding-3-large handles
    non-English reasonably — worth comparing against a multilingual-first
    model like Cohere's on this corpus's Bengali content specifically.
    """

    _DIMENSIONS = {
        "text-embedding-3-large": 3072,
        "text-embedding-3-small": 1536,
    }

    def __init__(self, model: str = "text-embedding-3-large", batch_size: int = 96, max_retries: int = 5):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("OpenAIEmbedder needs the openai package: run `uv add openai`") from e

        self.name = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.dimensions = self._DIMENSIONS.get(model, 3072)
        self._client = OpenAI()  # reads OPENAI_API_KEY from env

    def embed(self, texts: list[str]) -> np.ndarray:
        rows: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            rows.extend(_embed_with_retry(self._call, batch, self.max_retries, "openai"))
            vectors = normalise(np.array(rows, dtype=np.float32))

            if vectors.shape[1] != self.dimensions:
                raise ValueError(
                    f"Expected {self.dimensions} dimensions, got {vectors.shape[1]}"
                )

            return vectors

    def _call(self, batch: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self.name, input=batch)
        return [item.embedding for item in resp.data]


class CohereEmbedder:
    """Cohere's embeddings endpoint.

    Needs: `uv add cohere`, and `COHERE_API_KEY` set in the environment.
    embed-multilingual-v3.0 is trained explicitly for cross-lingual retrieval —
    a natural comparison point for OpenAI's model on this English/Bengali mix.

    NOTE: Cohere v3 models take an `input_type` argument that must differ
    between indexing ("search_document", used here) and querying
    ("search_query", used in retriever.py) — same model, deliberately
    different embedding call. Don't let that asymmetry get flattened away;
    it's not the "must match at query time" trap the module docstring warns
    about, it's an intentional part of how this specific model works.
    """

    def __init__(self, model: str = "embed-multilingual-v3.0", batch_size: int = 96, max_retries: int = 5):
        try:
            import cohere
        except ImportError as e:
            raise ImportError("CohereEmbedder needs the cohere package: run `uv add cohere`") from e

        self.name = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.dimensions = 1024  # embed-multilingual-v3.0's fixed output size
        self._client = cohere.Client()  # reads COHERE_API_KEY from env

    def embed(self, texts: list[str]) -> np.ndarray:
        rows: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            rows.extend(_embed_with_retry(self._call, batch, self.max_retries, "cohere"))
        return normalise(np.array(rows, dtype=np.float32))

    def _call(self, batch: list[str]) -> list[list[float]]:
        resp = self._client.embed(texts=batch, model=self.name, input_type="search_document")
        return resp.embeddings


class VoyageEmbedder:
    """Voyage AI's embeddings endpoint.

    Needs: `uv add voyageai`, and `VOYAGE_API_KEY` set in the environment.
    voyage-multilingual-2 is purpose-built for cross-lingual retrieval; the
    free tier (50M tokens on this model, 200M on voyage-3.5/voyage-3-large)
    comfortably covers this corpus many times over — good default to start
    trial-and-error with, since cost is a non-issue.

    NOTE: like Cohere, Voyage's `input_type` differs between indexing
    ("document", used here) and querying ("query", used in retriever.py) —
    same model, deliberately different call. Same asymmetry, different
    argument spelling — don't copy Cohere's string across by habit.
    """

    _DIMENSIONS = {
        "voyage-multilingual-2": 1024,
        "voyage-3.5": 1024,
        "voyage-3-large": 1024,  # default; supports up to 2048 via output_dimension
    }

    def __init__(self, model: str = "voyage-multilingual-2", batch_size: int = 96, max_retries: int = 5):
        try:
            import voyageai
        except ImportError as e:
            raise ImportError("VoyageEmbedder needs the voyageai package: run `uv add voyageai`") from e

        self.name = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.dimensions = self._DIMENSIONS.get(model, 1024)
        self._client = voyageai.Client()  # reads VOYAGE_API_KEY from env

    def embed(self, texts: list[str]) -> np.ndarray:
        rows: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            rows.extend(_embed_with_retry(self._call, batch, self.max_retries, "voyage"))
        return normalise(np.array(rows, dtype=np.float32))

    def _call(self, batch: list[str]) -> list[list[float]]:
        resp = self._client.embed(texts=batch, model=self.name, input_type="document")
        return resp.embeddings


class GeminiEmbedder:
    """Google's Gemini embeddings endpoint.

    Needs: `uv add google-genai`, and `GEMINI_API_KEY` (or `GOOGLE_API_KEY`)
    set in the environment. gemini-embedding-001 tops the MTEB multilingual
    leaderboard and supports 100+ languages — the other free-tier option
    worth comparing against Voyage and Cohere on the Bengali content.

    NOTE: this API doesn't batch multiple texts in one call the way the
    others do (`embed_content` takes one string's worth of `contents` per
    call in the stable SDK) — `_call` loops internally per batch, so this
    is slower wall-clock than the other embedders for the same batch_size.
    Worth checking the SDK's current batch support before relying on this
    for large re-runs; it may have changed since this was written.
    """

    def __init__(self, model: str = "gemini-embedding-001", batch_size: int = 32, max_retries: int = 5):
        try:
            from google import genai
        except ImportError as e:
            raise ImportError("GeminiEmbedder needs the google-genai package: run `uv add google-genai`") from e

        self.name = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.dimensions = 3072  # default; truncatable to 768/1536 via output_dimensionality
        self._client = genai.Client()  # reads GEMINI_API_KEY / GOOGLE_API_KEY from env

    def embed(self, texts: list[str]) -> np.ndarray:
        rows: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            rows.extend(
                _embed_with_retry(
                self._call,
                batch,
                self.max_retries,
                "gemini"
            )
        )

        vectors = normalise(np.array(rows, dtype=np.float32))

        if vectors.shape[1] != self.dimensions:
            raise ValueError(
                f"Expected {self.dimensions} dimensions, got {vectors.shape[1]}"
        )

        return vectors

    def _call(self, batch: list[str]) -> list[list[float]]:
        rows = []

        for text in batch:
            resp = self._client.models.embed_content(
                model=self.name,
                contents=text
            )

            rows.append(resp.embeddings[0].values)

        return rows


def build_embedder(provider: str = "", model: str = "", dimensions: int = 0) -> Embedder:
    """Map the `embedding_provider:` string in an index config to one of yours.

    `dimensions` is accepted for interface symmetry with config loading but
    unused here — neither provider lets you choose an arbitrary output size,
    so it's not threaded through. If a future provider supports Matryoshka
    truncation, wire it in there.
    """
    if provider == "openai":
        return OpenAIEmbedder(model=model) if model else OpenAIEmbedder()
    if provider == "cohere":
        return CohereEmbedder(model=model) if model else CohereEmbedder()
    if provider == "voyage":
        return VoyageEmbedder(model=model) if model else VoyageEmbedder()
    if provider == "gemini":
        return GeminiEmbedder(model=model) if model else GeminiEmbedder()
    raise ValueError(
        f"Unknown embedding_provider: {provider!r}. Supported: 'openai', 'cohere', 'voyage', 'gemini'."
    )