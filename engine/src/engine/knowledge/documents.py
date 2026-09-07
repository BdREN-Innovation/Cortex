"""pages.jsonl -> documents.jsonl.

Team B's first stage, and the boundary with Team A. It reads bytes that were
already captured, so it runs offline, in seconds, as many times as you like.
Tune it, re-run it, read the output, tune again — no network, no re-crawl,
nobody blocked.

Every row it emits is a `CleanDocument`: a page, or a PDF promoted to a document
of its own. From here down, nothing knows or cares which it was.

TEAM B OWNS THIS FILE.

Libraries worth considering
---------------------------
Nothing here is required — the scaffold ships with almost no dependencies and
these are suggestions, not a shortlist. Add what you choose with `uv add`.

Nothing new — this file is orchestration. It calls parsers.py, reads and writes
with contracts.jsonio, and uses pathlib.

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
    # "builtin" | "pdfplumber" | "docling" — see parsers.py.
    parser: str = "builtin"
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

    Split the records by type using `pdf.is_pdf(content_type, url)`:

    HTML pages
      * parse with the configured parser
      * DROP pages under `min_text_chars` — that is navigation, not content
      * DROP duplicate text by `content_hash`. This can only be judged here,
        on the text: "/" and "/index.html" are two captured records serving
        identical prose, and identical pages routinely differ in their HTML by
        a timestamp or a CSRF token. On the fixture site this collapses 7 captured
        records into 6 documents.
      * mirror tables to `run_dir/tables/<page_id>.<n>.md` when `save_tables`
      * carry `page.images` onto `assets` for provenance. Nothing downstream
        opens them — the embedders are text-only — but the alt text is already
        in the prose, which is the part that mattered.
      * emit doc_type="page"

    PDFs
      * parse with the configured parser; a scanned one yields "" and is
        dropped as thin, which is expected
      * emit doc_type="pdf" as its OWN row, so it chunks and cites like any
        other document
      * inherit the linking page's `section_path` (via `page.parent_url`) and
        append the PDF's own title, so a PDF answer cites as
        "Home > Docs > Plans > Refund Policy" rather than as a bare filename.
        Do the HTML pages first so those breadcrumbs exist to inherit.

    Every row must pass `CleanDocument.validate()` — the indexer refuses the
    whole file if one row fails, which blocks everyone downstream.

    Log a one-line summary: how many documents, how many were PDFs, how many
    were dropped as thin and as duplicates. Those four numbers are how you tell
    whether an extraction change helped.

    `out_path` defaults to `run_dir/documents.jsonl`, and is overridable so two
    parser configs can be compared side by side.
    """
    raise NotImplementedError
