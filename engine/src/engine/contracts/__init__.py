"""Frozen data contracts shared by the crawler, knowledge and evaluation teams.

Nothing in here may import from `engine.crawler`, `engine.knowledge` or
`engine.evaluation`. The dependency arrow points one way: teams depend on
contracts, never on each other. Changing a field here is a cross-team decision.
"""

from engine.contracts.documents import (
    ASSET_KINDS,
    DOC_TYPES,
    Asset,
    Chunk,
    CleanDocument,
    CrawledPage,
    CrawlManifest,
    RawAsset,
    RawPage,
)
from engine.contracts.retrieval import RetrievedChunk, Retriever
from engine.contracts.answers import Answer, Citation
from engine.contracts.evaluation import EvalCase, EvalResult, RunReport

__all__ = [
    "RawPage",
    "RawAsset",
    "Asset",
    "ASSET_KINDS",
    "DOC_TYPES",
    "CleanDocument",
    "CrawledPage",
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
