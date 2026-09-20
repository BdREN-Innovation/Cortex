"""Grounded RAG answering for dense, sparse or hybrid retrieval."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from engine.contracts.answers import Answer, Citation
from engine.contracts.retrieval import RetrievedChunk, Retriever


log = logging.getLogger(__name__)


REFUSAL_TEXT = (
    "I don't have enough information in the indexed content to answer that."
)


SYSTEM_PROMPT = f"""
You answer questions using ONLY the numbered evidence passages provided.

Rules:
- Base every factual claim only on the supplied evidence.
- Do not use outside knowledge.
- Do not guess.
- Cite evidence using [1], [2], [3], etc.
- Cite only passage numbers that were actually supplied.
- Keep the answer concise and factual.
- If the evidence is insufficient, output exactly:

{REFUSAL_TEXT}
""".strip()


@dataclass
class RagConfig:
    """
    Configuration for the RAG answering layer.

    Kept compatible with the existing Cortex CLI and evaluation YAML.
    """

    provider: str = ""
    model: str = ""
    top_k: int = 5
    min_score: float = 0.0
    max_context_chars: int = 8000
    temperature: float = 0.0

    @classmethod
    def from_dict(
        cls,
        payload: dict | None,
    ) -> "RagConfig":

        payload = payload or {}

        if "max_context_chars" in payload:
            max_context_chars = int(
                payload["max_context_chars"]
            )

        elif "max_context_tokens" in payload:
            # Backward compatibility with the experimental file.
            max_context_chars = int(
                payload["max_context_tokens"]
            ) * 4

        else:
            max_context_chars = 8000

        return cls(
            provider=str(
                payload.get(
                    "provider",
                    "",
                )
                or ""
            ),
            model=str(
                payload.get(
                    "model",
                    "",
                )
                or ""
            ),
            top_k=int(
                payload.get(
                    "top_k",
                    5,
                )
            ),
            min_score=float(
                payload.get(
                    "min_score",
                    0.0,
                )
            ),
            max_context_chars=max_context_chars,
            temperature=float(
                payload.get(
                    "temperature",
                    0.0,
                )
            ),
        )


def build_context(
    chunks: list[RetrievedChunk],
    max_chars: int,
) -> tuple[str, list[RetrievedChunk]]:
    """
    Build the numbered evidence block passed to the generator.

    Return:
        context text
        chunks actually visible to the generator
    """

    max_chars = max(
        0,
        int(max_chars),
    )

    if max_chars == 0:
        return "", []

    used: list[RetrievedChunk] = []
    parts: list[str] = []

    total = 0

    separator = "\n\n---\n\n"

    for chunk in chunks:

        number = len(used) + 1

        label = (
            chunk.title
            or chunk.canonical_url
            or chunk.chunk_id
        )

        block = (
            f"[{number}] {label}\n"
            f"{chunk.text.strip()}"
        )

        additional_length = len(block)

        if parts:
            additional_length += len(
                separator
            )

        if (
            total
            + additional_length
            > max_chars
        ):
            continue

        parts.append(block)
        used.append(chunk)

        total += additional_length

    return separator.join(parts), used


def _extractive_generate(
    used: list[RetrievedChunk],
) -> tuple[str, dict]:

    if not used:
        return REFUSAL_TEXT, {}

    return (
        used[0].text.strip(),
        {},
    )


def _gemini_generate(
    question: str,
    context: str,
    model: str,
    temperature: float,
) -> tuple[str, dict]:

    if not model:
        raise ValueError(
            "Gemini provider selected but no model was configured. "
            "Set rag.model or pass --model."
        )

    try:
        from google import genai
        from google.genai import types

    except ImportError as exc:

        raise ImportError(
            "Gemini generation requires google-genai. "
            "Install it with: uv add google-genai"
        ) from exc

    client = genai.Client()

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Evidence passages:\n"
        f"{context}\n\n"
        f"Question:\n"
        f"{question}\n\n"
        f"Answer:"
    )

    response = None
    for attempt in range(6):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=float(temperature)
                ),
            )
            break
        except Exception as exc:
            transient = any(code in str(exc) for code in ("429", "503", "500"))
            if not transient or attempt == 5:
                raise
            wait = 15 * (attempt + 1)
            log.warning("gemini busy (%s); retrying in %ss", str(exc)[:60], wait)
            time.sleep(wait)

    text = (
        getattr(
            response,
            "text",
            None,
        )
        or ""
    ).strip()

    usage: dict = {}

    metadata = getattr(
        response,
        "usage_metadata",
        None,
    )

    if metadata is not None:

        if hasattr(
            metadata,
            "model_dump",
        ):
            usage = metadata.model_dump(
                exclude_none=True
            )

        elif hasattr(
            metadata,
            "to_dict",
        ):
            usage = metadata.to_dict()

    return text, usage


def _generate(
    provider: str,
    model: str,
    question: str,
    context: str,
    used: list[RetrievedChunk],
    temperature: float,
) -> tuple[str, dict]:

    provider = (
        provider
        or "extractive"
    ).strip().lower()

    if provider == "extractive":

        return _extractive_generate(
            used
        )

    if provider in {
        "gemini",
        "google",
    }:

        return _gemini_generate(
            question=question,
            context=context,
            model=model,
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown RAG provider: {provider!r}. "
        "Supported: extractive, gemini."
    )


def _referenced_indices(
    text: str,
    n_available: int,
) -> list[int]:
    """
    Extract valid [n] citation markers from generated text.

    This helper is retained for compatibility/debugging, although Gemini
    source output preserves the complete original evidence numbering so the
    CLI source numbers always remain aligned with the numbers the model saw.
    """

    seen: list[int] = []

    for match in re.finditer(
        r"\[(\d+)\]",
        text or "",
    ):

        index = int(
            match.group(1)
        )

        if (
            1 <= index <= n_available
            and index not in seen
        ):
            seen.append(index)

    return seen


def _citation_from_chunk(
    chunk: RetrievedChunk,
) -> Citation:

    quote = chunk.text.strip()

    if len(quote) > 240:

        quote = quote[:240]

        if " " in quote:
            quote = quote.rsplit(
                " ",
                1,
            )[0]

        quote = quote.rstrip() + "…"

    return Citation(
        doc_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        canonical_url=chunk.canonical_url,
        title=chunk.title,
        section_path=list(
            chunk.section_path
        ),
        quote=quote,
    )


def _refusal_answer(
    *,
    question: str,
    retrieved: list[RetrievedChunk],
    provider: str,
    model: str,
    started: float,
    usage: dict | None = None,
) -> Answer:

    return Answer(
        question=question,
        text=REFUSAL_TEXT,
        citations=[],
        refused=True,
        retrieved_chunk_ids=[
            chunk.chunk_id
            for chunk in retrieved
        ],
        model=(
            model
            if provider != "extractive"
            else "extractive"
        ),
        provider=provider,
        latency_ms=int(
            (
                time.monotonic()
                - started
            )
            * 1000
        ),
        usage=usage or {},
    )


def answer(
    question: str,
    retriever: Retriever,
    config: RagConfig | None = None,
) -> Answer:
    """
    Retrieve, ground, generate, cite and refuse when unsupported.
    """

    config = config or RagConfig()

    started = time.monotonic()

    provider = (
        config.provider
        or "extractive"
    ).strip().lower()

    question = (
        question
        or ""
    ).strip()

    if not question:

        return _refusal_answer(
            question=question,
            retrieved=[],
            provider=provider,
            model=config.model,
            started=started,
        )

    retrieved = retriever.retrieve(
        question,
        top_k=max(
            0,
            int(config.top_k),
        ),
    )

    # IMPORTANT:
    # Dense cosine, BM25 and RRF scores have different scales.
    # Tune min_score separately for each retrieval mode.
    supported = [
        chunk
        for chunk in retrieved
        if float(chunk.score)
        >= float(config.min_score)
    ]

    if not supported:

        log.info(
            "refusing %r because no chunk passed min_score=%s",
            question,
            config.min_score,
        )

        return _refusal_answer(
            question=question,
            retrieved=retrieved,
            provider=provider,
            model=config.model,
            started=started,
        )

    context, used = build_context(
        supported,
        max_chars=config.max_context_chars,
    )

    if not used:

        return _refusal_answer(
            question=question,
            retrieved=retrieved,
            provider=provider,
            model=config.model,
            started=started,
        )

    text, usage = _generate(
        provider=provider,
        model=config.model,
        question=question,
        context=context,
        used=used,
        temperature=config.temperature,
    )

    # Gemini has been instructed to use this exact refusal string.
    if (
        not text
        or text.strip() == REFUSAL_TEXT
    ):

        return _refusal_answer(
            question=question,
            retrieved=retrieved,
            provider=provider,
            model=config.model,
            started=started,
            usage=usage,
        )

    if provider == "extractive":

        # Extractive output comes only from the best visible chunk.
        # Cite exactly that chunk.
        cited_chunks = [
            used[0]
        ]

    else:

        # IMPORTANT:
        # Keep the exact evidence ordering that Gemini saw.
        #
        # Example:
        # Gemini sees:
        #   [1] chunk A
        #   [2] chunk B
        #   [3] chunk C
        #   [4] chunk D
        #   [5] chunk E
        #
        # If Gemini answers using [5], the CLI must still print chunk E as
        # Source [5]. Filtering the citations down to only referenced chunks
        # would renumber them and make the citation dishonest/mismatched.
        #
        # Every chunk here was actually visible to the generator, so keeping
        # the full `used` list remains grounded and citation-safe.
        cited_chunks = used

    return Answer(
        question=question,
        text=text,
        citations=[
            _citation_from_chunk(
                chunk
            )
            for chunk in cited_chunks
        ],
        refused=False,
        retrieved_chunk_ids=[
            chunk.chunk_id
            for chunk in retrieved
        ],
        model=(
            config.model
            if provider != "extractive"
            else "extractive"
        ),
        provider=provider,
        latency_ms=int(
            (
                time.monotonic()
                - started
            )
            * 1000
        ),
        usage=usage,
    )