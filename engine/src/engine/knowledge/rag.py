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
from dataclasses import dataclass

from engine.contracts.answers import Answer, Citation  # noqa: F401 - Citation is yours to build
from engine.contracts.retrieval import RetrievedChunk, Retriever

log = logging.getLogger(__name__)

# The instruction that does the actual work. Grounding and refusal are prompt
# decisions before they are code decisions, so this is some of the
# highest-leverage text in the project. Write it, then change it only with
# Team C's scorecard in front of you.
SYSTEM_PROMPT = ""

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
        raise NotImplementedError


def build_context(chunks: list[RetrievedChunk], max_chars: int) -> tuple[str, list[RetrievedChunk]]:
    """Pack chunks into a prompt under a budget.

    It returns two things on purpose: the context, and the chunks that actually
    fitted. Citations must reflect what the model could see, not what you
    retrieved and then truncated away — citing a document the model never read
    is the subtlest bug in this pipeline.
    """
    raise NotImplementedError


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
    raise NotImplementedError
