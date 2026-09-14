"""Retrieve, ground, cite.

The last stage: take a question, find the relevant chunks, and answer using
ONLY those chunks. Two behaviours are graded by Team C and both matter:
citations must point at the documents the answer actually came from, and an
unanswerable question must be REFUSED rather than answered confidently. A
confident wrong answer scores worse than "I don't know".

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
* Which generation provider, and which model? Or none — returning the best
  retrieved passage verbatim is a legitimate baseline and needs no API key.
  Build that first: it tells you whether RETRIEVAL works before you start
  paying for generation.
* What does the prompt say? Grounding and refusal are prompt decisions before
  they are code decisions. This is the highest-leverage text in the project and
  it is worth iterating on with Team C's scorecard in front of you.
* When should the system refuse? There is a threshold below which the retrieved
  context does not support an answer. Too low and you hallucinate; too high and
  you refuse real questions. Where is it, and how did you find it?
* How much context fits in the prompt, and what do you drop when it does not
  fit? Whatever you drop must also drop out of the citations — citing a
  document the model never saw is the subtlest bug in this pipeline.
* What does a citation point at: the chunk, the document, a quote inside it?

"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from engine.contracts.answers import Answer, Citation
from engine.contracts.retrieval import RetrievedChunk, Retriever

log = logging.getLogger(__name__)

# The instruction that does the actual work. Grounding and refusal are prompt
# decisions before they are code decisions, so this is some of the
# highest-leverage text in the project. Write it, then change it only with
# Team C's scorecard in front of you.
SYSTEM_PROMPT = (
    "You answer questions about a university or research-network website using "
    "ONLY the numbered context passages provided below. Every factual claim you "
    "make must be supported by at least one passage — cite it inline as [1], [2] "
    "etc., matching the passage numbers you were given. Do not use outside "
    "knowledge, and do not guess. If the passages do not contain enough "
    "information to answer the question, say plainly that you don't have enough "
    "information, rather than producing a plausible-sounding guess. Keep answers "
    "short and factual."
)

# The exact text returned when the system declines to answer. A constant, not a
# literal scattered through the code, because Team C's harness matches on it —
# change the wording here and their unanswerable cases keep working.
REFUSAL = "I don't have enough information in the indexed content to answer that."


@dataclass
class RagConfig:
    # Which generator to use. The names are yours to define in this file.
    provider: str = ""
    model: str = ""
    top_k: int = 5
    # Below this retrieval score, nothing is considered relevant and the
    # answer must be a refusal. There is no right default — find it against
    # Team C's unanswerable cases.
    min_score: float = 0.0
    max_context_chars: int = 8000
    temperature: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict) -> "RagConfig":
        return cls(
            provider=payload.get("provider", ""),
            model=payload.get("model", ""),
            top_k=payload.get("top_k", 5),
            min_score=payload.get("min_score", 0.0),
            max_context_chars=payload.get("max_context_chars", 8000),
            temperature=payload.get("temperature", 0.0),
        )


def build_context(chunks: list[RetrievedChunk], max_chars: int) -> tuple[str, list[RetrievedChunk]]:
    """Pack chunks into a prompt under a budget.

    It returns two things on purpose: the context, and the chunks that actually
    fitted. Citations must reflect what the model could see, not what you
    retrieved and then truncated away — citing a document the model never read
    is the subtlest bug in this pipeline.

    A chunk that alone is bigger than the whole budget is truncated rather
    than dropped outright, but only for the *first* chunk — an empty context
    would force a refusal even though something relevant was actually found.
    """
    parts: list[str] = []
    used: list[RetrievedChunk] = []
    total = 0

    for position, chunk in enumerate(chunks, start=1):
        header = f"[{position}] {chunk.title or chunk.canonical_url}\n"
        remaining = max_chars - total - len(header)
        if remaining <= 0:
            break

        text = chunk.text
        if len(text) > remaining:
            if used:
                # Later chunks just get dropped rather than sliced thin —
                # a half-sentence of context is worse than no context.
                break
            text = text[:remaining]

        block = f"{header}{text}\n"
        parts.append(block)
        used.append(chunk)
        total += len(block)

    return "\n".join(parts), used


def _generate_extractive(context_chunks: list[RetrievedChunk]) -> str:
    """No API key, no generation — just the best-matching passage, verbatim.
    A legitimate baseline: it answers "did retrieval find the right thing"
    before a single token is spent on generation."""
    top = context_chunks[0]
    text = top.text.strip()
    return text[:1000]


def _generate_openai(
    question: str, context: str, model: str, temperature: float
) -> tuple[str, dict]:
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(
            "the 'openai' rag provider needs the openai package: run `uv add openai`"
        ) from e

    client = OpenAI()  # reads OPENAI_API_KEY from the environment
    resp = client.chat.completions.create(
        model=model or "gpt-4o-mini",
        temperature=temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\nQuestion: {question}"},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    usage = dict(resp.usage) if resp.usage else {}
    return text, usage


def answer(question: str, retriever: Retriever, config: RagConfig | None = None) -> Answer:
    """Answer a question from the knowledge base.

    Retrieve, decide whether the context actually supports an answer, and
    either generate one from it or refuse. Both outcomes are graded by Team C,
    and refusing well is a feature rather than a failure.

    The returned Answer is what everything downstream sees, and **it must carry
    citations**. That is the deliverable — an answer a reader cannot verify is
    worth very little, and Team C scores it directly.

    Every citation has to point at something the model actually read. If you
    dropped chunks to fit a context budget, those references drop with them.
    A refusal carries no citations, which is correct: there was nothing to cite.

    Also record latency and token usage, even when it feels pointless — they are
    the only way to answer "why is this slow" and "why did this cost that much"
    when somebody asks on day twelve.
    """
    config = config or RagConfig()
    provider = config.provider or "extractive"
    started = time.monotonic()

    retrieved = retriever.retrieve(question, top_k=config.top_k)
    relevant = [chunk for chunk in retrieved if chunk.score >= config.min_score]

    if not relevant:
        return Answer(
            question=question,
            text=REFUSAL,
            citations=[],
            refused=True,
            retrieved_chunk_ids=[chunk.chunk_id for chunk in retrieved],
            model=config.model,
            provider=provider,
            latency_ms=int((time.monotonic() - started) * 1000),
            usage={},
        )

    context, used = build_context(relevant, config.max_context_chars)

    usage: dict = {}
    if provider == "extractive":
        text = _generate_extractive(used)
    elif provider == "openai":
        text, usage = _generate_openai(question, context, config.model, config.temperature)
    else:
        raise ValueError(f"Unknown rag provider: {provider!r}. Supported: 'extractive', 'openai'.")

    citations = [
        Citation(
            doc_id=chunk.doc_id,
            chunk_id=chunk.chunk_id,
            canonical_url=chunk.canonical_url,
            title=chunk.title,
            section_path=list(chunk.section_path),
            quote=chunk.text[:280],
        )
        for chunk in used
    ]

    return Answer(
        question=question,
        text=text,
        citations=citations,
        refused=False,
        retrieved_chunk_ids=[chunk.chunk_id for chunk in retrieved],
        model=config.model,
        provider=provider,
        latency_ms=int((time.monotonic() - started) * 1000),
        usage=usage,
    )