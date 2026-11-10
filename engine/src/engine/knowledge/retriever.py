"""Dense, sparse and hybrid retrieval for Cortex."""

from __future__ import annotations

import logging
import math
import os
import re
from collections import defaultdict
from pathlib import Path

from engine.contracts.documents import Chunk
from engine.contracts.jsonio import read_jsonl
from engine.contracts.retrieval import RetrievedChunk
from engine.knowledge.embedding import Embedder, build_embedder
from engine.knowledge.store import NumpyStore, QdrantStore, load_index_meta


log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_VALID_MODES = {"dense", "sparse", "hybrid"}


def _clean_question(question: str) -> str:
    return re.sub(r"\s+", " ", question or "").strip()


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _to_retrieved(chunk: Chunk, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        text=chunk.text,
        score=float(score),
        canonical_url=chunk.canonical_url,
        title=chunk.title,
        section_path=list(chunk.section_path),
    )


# ============================================================
# DENSE RETRIEVAL
# ============================================================


class DenseRetriever:
    """Cohere query embedding + existing vector-store search."""

    def __init__(self, store, embedder: Embedder, index_id: str = ""):
        self.store = store
        self.embedder = embedder
        self.index_id = index_id

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:

        question = _clean_question(question)
        top_k = max(0, int(top_k))

        if not question or top_k == 0:
            return []

        vector = self.embedder.embed([question])[0]

        results = self.store.search(
            vector,
            top_k,
        )

        return [
            _to_retrieved(chunk, score)
            for chunk, score in results
        ]


# Keep compatibility with existing project imports.
VectorRetriever = DenseRetriever


# ============================================================
# SPARSE RETRIEVAL — BM25
# ============================================================


class SparseRetriever:
    """BM25 lexical retriever implemented without an external BM25 library."""

    def __init__(
        self,
        chunks: list[Chunk],
        k1: float = 1.5,
        b: float = 0.75,
    ):
        if k1 <= 0:
            raise ValueError("BM25 k1 must be greater than 0")

        if not 0 <= b <= 1:
            raise ValueError("BM25 b must be between 0 and 1")

        self.k1 = float(k1)
        self.b = float(b)

        self._chunks = list(chunks)

        self._doc_tokens = [
            _tokenize(chunk.text)
            for chunk in self._chunks
        ]

        self._doc_len = [
            len(tokens)
            for tokens in self._doc_tokens
        ]

        self._avgdl = (
            sum(self._doc_len) / len(self._doc_len)
            if self._doc_len
            else 0.0
        )

        # term -> {document index -> frequency}
        self._postings: dict[str, dict[int, int]] = defaultdict(dict)

        for doc_idx, tokens in enumerate(self._doc_tokens):

            frequencies: dict[str, int] = defaultdict(int)

            for token in tokens:
                frequencies[token] += 1

            for token, frequency in frequencies.items():
                self._postings[token][doc_idx] = frequency

        n_docs = len(self._doc_tokens)

        self._idf: dict[str, float] = {
            term: math.log(
                (
                    n_docs
                    - len(postings)
                    + 0.5
                )
                / (
                    len(postings)
                    + 0.5
                )
                + 1.0
            )
            for term, postings in self._postings.items()
        }

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:

        question = _clean_question(question)
        top_k = max(0, int(top_k))

        if not question or not self._chunks or top_k == 0:
            return []

        scores: dict[int, float] = defaultdict(float)

        # Score each unique query term once.
        query_terms = dict.fromkeys(
            _tokenize(question)
        )

        for term in query_terms:

            postings = self._postings.get(term)
            idf = self._idf.get(term)

            if not postings or idf is None:
                continue

            for doc_idx, frequency in postings.items():

                doc_length = self._doc_len[doc_idx]

                denominator = (
                    frequency
                    + self.k1
                    * (
                        1.0
                        - self.b
                        + self.b
                        * doc_length
                        / (
                            self._avgdl
                            if self._avgdl > 0
                            else 1.0
                        )
                    )
                )

                scores[doc_idx] += (
                    idf
                    * frequency
                    * (self.k1 + 1.0)
                    / denominator
                )

        ranked = sorted(
            scores.items(),
            key=lambda item: (
                -item[1],
                self._chunks[item[0]].chunk_id,
            ),
        )[:top_k]

        return [
            _to_retrieved(
                self._chunks[doc_idx],
                score,
            )
            for doc_idx, score in ranked
        ]

    @classmethod
    def load(
        cls,
        chunks_path: str | Path,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> "SparseRetriever":

        chunks_path = Path(chunks_path)

        if not chunks_path.exists():
            raise FileNotFoundError(
                f"{chunks_path} does not exist. "
                "Sparse retrieval requires the chunks.jsonl "
                "for the same corpus used by dense retrieval."
            )

        chunks = list(
            read_jsonl(
                chunks_path,
                factory=Chunk.from_dict,
            )
        )

        log.info(
            "loaded %d chunks for BM25 from %s",
            len(chunks),
            chunks_path,
        )

        return cls(
            chunks,
            k1=k1,
            b=b,
        )


# ============================================================
# HYBRID RETRIEVAL — RRF
# ============================================================


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    k: int = 60,
) -> list[RetrievedChunk]:

    if k < 0:
        raise ValueError("RRF k must be >= 0")

    fused_scores: dict[str, float] = defaultdict(float)
    chunks_by_id: dict[str, RetrievedChunk] = {}

    for ranked in ranked_lists:

        for rank, chunk in enumerate(
            ranked,
            start=1,
        ):
            fused_scores[chunk.chunk_id] += (
                1.0 / (k + rank)
            )

            chunks_by_id.setdefault(
                chunk.chunk_id,
                chunk,
            )

    ordered_ids = sorted(
        fused_scores,
        key=lambda chunk_id: (
            -fused_scores[chunk_id],
            chunk_id,
        ),
    )

    return [
        RetrievedChunk(
            chunk_id=chunks_by_id[chunk_id].chunk_id,
            doc_id=chunks_by_id[chunk_id].doc_id,
            text=chunks_by_id[chunk_id].text,
            score=float(
                fused_scores[chunk_id]
            ),
            canonical_url=(
                chunks_by_id[chunk_id].canonical_url
            ),
            title=chunks_by_id[chunk_id].title,
            section_path=list(
                chunks_by_id[chunk_id].section_path
            ),
        )
        for chunk_id in ordered_ids
    ]


class HybridRetriever:
    """Dense + BM25 candidates combined using RRF."""

    def __init__(
        self,
        dense: DenseRetriever,
        sparse: SparseRetriever,
        candidate_k: int = 20,
        rrf_k: int = 60,
    ):
        self.dense = dense
        self.sparse = sparse
        self.candidate_k = max(
            1,
            int(candidate_k),
        )
        self.rrf_k = max(
            0,
            int(rrf_k),
        )

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:

        question = _clean_question(question)
        top_k = max(0, int(top_k))

        if not question or top_k == 0:
            return []

        candidate_k = max(
            top_k,
            self.candidate_k,
        )

        dense_hits = self.dense.retrieve(
            question,
            top_k=candidate_k,
        )

        sparse_hits = self.sparse.retrieve(
            question,
            top_k=candidate_k,
        )

        fused = reciprocal_rank_fusion(
            [
                dense_hits,
                sparse_hits,
            ],
            k=self.rrf_k,
        )

        return fused[:top_k]


# ============================================================
# LOADING
# ============================================================


def _selected_mode(config: dict) -> str:
    """
    Priority:
    1. RETRIEVAL_MODE environment variable
    2. index metadata config
    3. dense
    """

    mode = (
        os.environ.get("RETRIEVAL_MODE")
        or config.get("retrieval_mode")
        or "dense"
    )

    mode = str(mode).strip().lower()

    if mode not in _VALID_MODES:
        raise ValueError(
            f"Unknown retrieval mode {mode!r}. "
            "Use dense, sparse, or hybrid."
        )

    return mode


def _resolve_corpus_path(
    *,
    index_dir: Path,
    site: str,
    corpus_root: str | Path,
    corpus_path: str | Path | None,
) -> Path:

    explicit_path = (
        corpus_path
        or os.environ.get(
            "RETRIEVAL_CORPUS_PATH"
        )
    )

    if explicit_path:

        path = Path(explicit_path)

        if path.exists():
            return path

        raise FileNotFoundError(
            f"Corpus file does not exist: {path}"
        )

    candidates = [
        index_dir / "chunks.jsonl",
        Path(corpus_root)
        / site
        / "chunks.jsonl",
    ]

    for path in candidates:
        if path.exists():
            return path

    attempted = "\n".join(
        f" - {path}"
        for path in candidates
    )

    raise FileNotFoundError(
        "Could not find chunks.jsonl for sparse/hybrid retrieval.\n"
        f"Tried:\n{attempted}\n\n"
        "Set RETRIEVAL_CORPUS_PATH to the chunks.jsonl "
        "for the SAME corpus used by dense retrieval."
    )


def _build_dense(
    meta,
    config: dict,
    index_dir: Path,
) -> DenseRetriever:

    embedder = build_embedder(
        provider=config.get(
            "embedding_provider",
            "",
        ),
        model=config.get(
            "embedding_model",
            "",
        ),
        dimensions=meta.dimensions,
    )

    if embedder.dimensions != meta.dimensions:
        raise ValueError(
            f"{index_dir}: query embedder has "
            f"{embedder.dimensions} dimensions "
            f"but the index has {meta.dimensions}"
        )

    backend = meta.backend or "numpy"

    if backend == "numpy":

        store = NumpyStore.load(
            index_dir
        )

    elif backend == "qdrant":

        store = QdrantStore(
            collection=meta.collection,
            dimensions=meta.dimensions,
            ensure=False,
        )

    else:

        raise ValueError(
            f"Unknown index backend: {backend!r}"
        )

    return DenseRetriever(
        store=store,
        embedder=embedder,
        index_id=meta.index_id,
    )


def load_retriever(
    index_dir: str | Path,
    corpus_root: str | Path = "scratch/corpus",
    corpus_path: str | Path | None = None,
) -> DenseRetriever | SparseRetriever | HybridRetriever:

    index_dir = Path(index_dir)

    meta = load_index_meta(
        index_dir
    )

    config = meta.config or {}

    mode = _selected_mode(
        config
    )

    log.info(
        "loading index %s in %s mode",
        meta.index_id,
        mode,
    )

    # Sparse does not require Cohere/Qdrant.
    if mode == "sparse":

        chunks_path = _resolve_corpus_path(
            index_dir=index_dir,
            site=meta.site,
            corpus_root=corpus_root,
            corpus_path=corpus_path,
        )

        return SparseRetriever.load(
            chunks_path
        )

    dense = _build_dense(
        meta,
        config,
        index_dir,
    )

    if mode == "dense":
        return dense

    # Hybrid retrieval
    chunks_path = _resolve_corpus_path(
        index_dir=index_dir,
        site=meta.site,
        corpus_root=corpus_root,
        corpus_path=corpus_path,
    )

    sparse = SparseRetriever.load(
        chunks_path
    )

    return HybridRetriever(
        dense=dense,
        sparse=sparse,
        candidate_k=int(
            config.get(
                "hybrid_candidate_k",
                20,
            )
        ),
        rrf_k=int(
            config.get(
                "rrf_k",
                60,
            )
        ),
    )