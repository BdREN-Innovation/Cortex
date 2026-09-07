"""Embedding providers behind one interface.

Note for the team: Anthropic does not ship a first-party embeddings endpoint,
so `anthropic` is a *generation* provider only. Embeddings come from OpenAI, or
from the built-in deterministic hashing embedder.

`hash` is not a good retriever — it is a lexical approximation with no semantic
understanding. It exists so the whole pipeline runs offline, in CI, and on a
laptop with no API key, which is what lets teams 2 and 3 work in parallel.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class Embedder(Protocol):
    dimensions: int
    name: str

    def embed(self, texts: list[str]) -> np.ndarray:
        ...


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class HashEmbedder:
    """Deterministic bag-of-words hashing (the 'hashing trick'). No network, no keys."""

    def __init__(self, dimensions: int = 512):
        self.dimensions = dimensions
        self.name = f"hash-{dimensions}"

    @staticmethod
    def _tokens(text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        # Unigrams plus bigrams: bigrams give the vectors a little word order.
        return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in self._tokens(text):
                digest = hashlib.md5(token.encode()).digest()
                bucket = int.from_bytes(digest[:4], "little") % self.dimensions
                sign = 1.0 if digest[4] % 2 else -1.0
                matrix[row, bucket] += sign
        return _normalise(matrix)


class OpenAIEmbedder:
    """Real semantic embeddings. Requires OPENAI_API_KEY and the `openai` extra."""

    def __init__(self, model: str = "text-embedding-3-small", dimensions: int = 1536):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "The openai package is not installed. Run: uv pip install --python venv '.[openai]'"
            ) from exc
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set (see engine/.env.example)")
        self._client = OpenAI()
        self.model = model
        self.dimensions = dimensions
        self.name = model

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        # The endpoint takes batches; 128 keeps request bodies comfortable.
        for start in range(0, len(texts), 128):
            batch = texts[start : start + 128]
            response = self._client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        return _normalise(np.asarray(vectors, dtype=np.float32))


def build_embedder(provider: str = "hash", model: str = "", dimensions: int = 512) -> Embedder:
    provider = (provider or "hash").strip().lower()
    if provider == "hash":
        return HashEmbedder(dimensions=dimensions or 512)
    if provider == "openai":
        return OpenAIEmbedder(model=model or "text-embedding-3-small")
    raise ValueError(
        f"Unknown embedding provider {provider!r}. Supported: hash, openai. "
        "Anthropic has no embeddings API — use it for generation only."
    )
