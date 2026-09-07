"""Retrieve, ground, cite.

The last stage: take a question, find the relevant chunks, and answer using
ONLY those chunks. Two behaviours are graded by Team C and both matter:
citations must point at the documents the answer actually came from, and an
unanswerable question must be REFUSED rather than answered confidently. A
confident wrong answer scores worse than "I don't know".

TEAM B OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

openai      `uv add openai`. client.chat.completions.create(...)
anthropic   `uv add anthropic`. client.messages.create(...)
            Note the different shapes: Anthropic takes `system` as a top-level
            argument, not as a message in the list.
Both are optional extras — import them lazily so the default path needs neither.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from engine.contracts.answers import Answer, Citation
from engine.contracts.retrieval import RetrievedChunk, Retriever

log = logging.getLogger(__name__)

# The instruction that does the actual work. Grounding and refusal are prompt
# decisions before they are code decisions — spend time here, and change it
# only with Team C's scorecard in front of you.
SYSTEM_PROMPT = """\
You answer strictly from the provided context.
If the context does not contain the answer, say you do not know.
Never use outside knowledge. Cite the sources you used."""

# The exact text returned when the system declines to answer. A constant, not a
# literal scattered through the code, because Team C's harness matches on it —
# change the wording here and their unanswerable cases keep working.
REFUSAL = "I don't have enough information in the indexed content to answer that."


@dataclass
class RagConfig:
    provider: str = "extractive"  # extractive | openai | anthropic
    model: str = ""
    top_k: int = 5
    # Below this retrieval score, nothing is considered relevant and the
    # answer must be a refusal. Tune it against Team C's unanswerable cases:
    # too low and you hallucinate, too high and you refuse real questions.
    min_score: float = 0.05
    max_context_chars: int = 8000
    temperature: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict) -> "RagConfig":
        raise NotImplementedError


def build_context(chunks: list[RetrievedChunk], max_chars: int) -> tuple[str, list[RetrievedChunk]]:
    """Pack chunks into a prompt under a character budget.

    Return both the context string AND the chunks that actually fitted — the
    citations must reflect what the model could see, not what you retrieved and
    then truncated away. Getting this wrong produces citations to documents the
    model never read, which is the subtlest bug in the whole pipeline.

    Label each chunk in the context (e.g. "[1] ...") so the model can refer to
    them.
    """
    raise NotImplementedError


def answer(question: str, retriever: Retriever, config: RagConfig | None = None) -> Answer:
    """Answer a question from the knowledge base.

    Flow:
      1. Retrieve top_k chunks.
      2. If nothing came back, or the best score is below `min_score`, return
         an Answer with refused=True and no citations. Do not call the model —
         there is nothing to ground an answer in.
      3. Build the context from the chunks that fit.
      4. Generate:
         * "extractive" — no API key, no network: return the best chunk's text
           verbatim. This is the default so the pipeline is runnable by
           everyone from day one. It is a plumbing tool, not a good answer.
         * "openai" / "anthropic" — the real generators.
      5. Return an Answer carrying `citations`, `retrieved_chunk_ids`,
         `provider`, `model`, `latency_ms` and token `usage` if available.

    Record latency and usage even when it seems pointless — they are the only
    way to answer "why is this slow" and "why did this cost that much" later.
    """
    raise NotImplementedError
