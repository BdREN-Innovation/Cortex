"""Retrieve -> prompt -> answer, with citations that the eval harness can grade.

Generation providers mirror what the Cortex app already supports: openai and
anthropic, keyed from OPENAI_API_KEY / ANTHROPIC_API_KEY. `extractive` needs no
provider at all: it returns the retrieved passages verbatim, which keeps the
pipeline runnable offline and gives retrieval metrics something to score.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

from engine.contracts.answers import Answer, Citation
from engine.contracts.retrieval import RetrievedChunk, Retriever

log = logging.getLogger(__name__)

REFUSAL = "The provided context does not contain enough information to answer that."

SYSTEM_PROMPT = """You answer strictly from the numbered context passages provided.

Rules:
- Use only facts present in the context. Never rely on outside knowledge.
- Cite the passages you used as [1], [2] and so on, inline.
- If the context does not contain the answer, reply with exactly:
  "{refusal}"
- Be concise and concrete.""".format(refusal=REFUSAL)


@dataclass
class RagConfig:
    provider: str = "extractive"      # extractive | openai | anthropic
    model: str = ""
    top_k: int = 5
    # Chunks scoring below this are treated as noise. With the hash embedder,
    # scores are lexical overlap, so this doubles as the "do I know?" gate.
    min_score: float = 0.05
    max_context_chars: int = 8000
    temperature: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict) -> "RagConfig":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in payload.items() if k in known})


def build_context(chunks: list[RetrievedChunk], max_chars: int) -> tuple[str, list[RetrievedChunk]]:
    blocks, used, total = [], [], 0
    for index, chunk in enumerate(chunks, start=1):
        header = f"[{index}] {chunk.title or chunk.canonical_url}"
        if chunk.section_path:
            header += f" ({' > '.join(chunk.section_path)})"
        block = f"{header}\n{chunk.text}"
        if total + len(block) > max_chars and used:
            break
        blocks.append(block)
        used.append(chunk)
        total += len(block)
    return "\n\n---\n\n".join(blocks), used


def _citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            doc_id=chunk.doc_id,
            chunk_id=chunk.chunk_id,
            canonical_url=chunk.canonical_url,
            title=chunk.title,
            section_path=chunk.section_path,
            quote=chunk.text[:240].strip(),
        )
        for chunk in chunks
    ]


def answer(question: str, retriever: Retriever, config: RagConfig | None = None) -> Answer:
    config = config or RagConfig()
    started = time.monotonic()

    retrieved = retriever.retrieve(question, top_k=config.top_k)
    relevant = [c for c in retrieved if c.score >= config.min_score]

    if not relevant:
        return Answer(
            question=question,
            text=REFUSAL,
            refused=True,
            retrieved_chunk_ids=[c.chunk_id for c in retrieved],
            provider=config.provider,
            model=config.model,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    context, used = build_context(relevant, config.max_context_chars)

    if config.provider == "extractive":
        text = "\n\n".join(f"[{i}] {c.text.strip()}" for i, c in enumerate(used, start=1))
        usage: dict = {}
    elif config.provider == "openai":
        text, usage = _generate_openai(question, context, config)
    elif config.provider == "anthropic":
        text, usage = _generate_anthropic(question, context, config)
    else:
        raise ValueError(
            f"Unknown generation provider {config.provider!r}. "
            "Supported: extractive, openai, anthropic."
        )

    return Answer(
        question=question,
        text=text,
        citations=_citations(used),
        refused=REFUSAL.lower() in text.lower(),
        retrieved_chunk_ids=[c.chunk_id for c in retrieved],
        provider=config.provider,
        model=config.model,
        latency_ms=int((time.monotonic() - started) * 1000),
        usage=usage,
    )


def _user_prompt(question: str, context: str) -> str:
    return f"Context passages:\n\n{context}\n\nQuestion: {question}"


def _generate_openai(question: str, context: str, config: RagConfig) -> tuple[str, dict]:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError("Install the openai extra: uv pip install --python venv '.[openai]'") from exc
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI()
    response = client.chat.completions.create(
        model=config.model or "gpt-4o-mini",
        temperature=config.temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(question, context)},
        ],
    )
    usage = response.usage.model_dump() if response.usage else {}
    return response.choices[0].message.content or "", usage


def _generate_anthropic(question: str, context: str, config: RagConfig) -> tuple[str, dict]:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError(
            "Install the anthropic extra: uv pip install --python venv '.[anthropic]'"
        ) from exc
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.model or "claude-sonnet-5",
        max_tokens=1024,
        temperature=config.temperature,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(question, context)}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return text, usage
