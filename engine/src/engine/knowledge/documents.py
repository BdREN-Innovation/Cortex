"""pages.jsonl -> documents.jsonl.

Team B's first stage, and the boundary with Team A. It reads bytes that were
already captured, so it runs offline, in seconds, as many times as you like.
Tune it, re-run it, read the output, tune again — no network, no re-crawl,
nobody blocked.

Every row it emits is a `CleanDocument`: a page, or a PDF promoted to a document
of its own. From here down, nothing knows or cares which it was.

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
* Two captured records can hold identical prose (`/` and `/index.html` almost
  always do). How do you detect that, and which one wins?
* How short is too short? Navigation pages and cookie interstitials have text,
  it is just worthless. Where is your threshold and how did you pick it?
* A PDF becomes its own document — what is its breadcrumb? It has no page of
  its own, but it was linked from somewhere.
* What do you log? The counts here — documents out, PDFs among them, how many
  dropped and why — are how you tell whether an extraction change helped.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from engine.knowledge.extraction import SiteSelectors

log = logging.getLogger(__name__)


@dataclass
class ExtractConfig:
    """Read from `configs/extract.<site>.yaml`."""

    # A page shorter than this is navigation, not content.
    min_text_chars: int = 200
    # Mirror each table to tables/ as markdown. They are always inlined into the
    # document text regardless; this is only the inspection copy.
    save_tables: bool = True
    # Names one of the parsers you register in parsers.py.
    parser: str = ""
    # Per-site overrides for when the generic extractor gets a page wrong.
    selectors: SiteSelectors = field(default_factory=SiteSelectors)

    @classmethod
    def from_dict(cls, payload: dict) -> "ExtractConfig":
        """Build from parsed YAML; the nested `selectors:` block becomes SiteSelectors."""
        raise NotImplementedError


def extract_documents(
    run_dir: str | Path,
    config: ExtractConfig | None = None,
    out_path: str | Path | None = None,
) -> Path:
    """Read a crawl run and write documents.jsonl beside it.

    Input is the run directory Team A produced. Read `pages.jsonl`, and for
    each record open the bytes at `run_dir / page.content_path`.

    Two kinds of record come in and both become `CleanDocument` rows, so that
    from here down nothing knows or cares which was which:

      * an HTML page -> doc_type "page"
      * a linked PDF -> doc_type "pdf", a document in its own right rather than
        something glued onto the page that linked it

    Along the way you decide what does not deserve to be a document at all —
    see the questions at the top of this file.

    Every row must pass `CleanDocument.validate()` — the indexer refuses the
    whole file if one row fails, which blocks everyone downstream.

    Log a one-line summary: how many documents, how many were PDFs, how many
    were dropped as thin and as duplicates. Those four numbers are how you tell
    whether an extraction change helped.

    `out_path` defaults to `run_dir/documents.jsonl`, and is overridable so two
    parser configs can be compared side by side.
    """
    raise NotImplementedError
