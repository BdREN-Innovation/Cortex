"""Frozen data contracts shared by the crawler, knowledge and evaluation teams.

Nothing in here may import from `engine.crawler`, `engine.knowledge` or
`engine.evaluation`. The dependency arrow points one way: teams depend on
contracts, never on each other. Changing a field here is a cross-team decision.
"""

from engine.contracts.documents import Chunk, CleanDocument, RawPage, CrawlManifest
from engine.contracts.retrieval import RetrievedChunk, Retriever
from engine.contracts.answers import Answer, Citation
from engine.contracts.evaluation import EvalCase, EvalResult, RunReport

__all__ = [
    "RawPage",
    "CleanDocument",
    "Chunk",
    "CrawlManifest",
    "RetrievedChunk",
    "Retriever",
    "Answer",
    "Citation",
    "EvalCase",
    "EvalResult",
    "RunReport",
]
