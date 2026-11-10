"""scratch/build_eval_candidates.py

Doesn't invent an eval set — it samples real chunks from the corpus and
prints them so you can read actual content and write natural queries against
it, instead of guessing what's in there. Run once, review the output, then
hand-write query/answer pairs into eval_queries.jsonl using the chunk_ids
shown here.

chunk_document(doc: CleanDocument, config=None) -> list[Chunk] — takes a
CleanDocument OBJECT, not a raw dict, and returns a list of Chunk DATACLASS
instances, per the real chunking.py. Each JSON line from documents.clean.jsonl
is reconstructed into a CleanDocument before chunking; each returned Chunk is
converted to a dict via dataclasses.asdict() for everything below this point.

WATCH THIS: chunk_document() reads doc.canonical_url, but documents.py's
_process_pdf/_process_docx/_process_html never set a canonical_url field when
constructing CleanDocument (they set url, not canonical_url) — and
documents.py currently builds from a TEMPORARY stub
(scratch/contracts_stub.py), not the real engine.contracts.documents that
chunking.py imports. If the stub's CleanDocument doesn't define
canonical_url (or default it from url), CleanDocument(**raw) below will raise
a TypeError for a missing/unexpected argument. Check this directly rather
than assuming either way — it's a real gap between the stub and the real
contract, not something fixable from this script alone.

Usage:
    uv run python -m scratch.build_eval_candidates
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path

from engine.knowledge.chunking import chunk_document
from engine.contracts.documents import CleanDocument  # the real contract chunking.py expects

CORPUS_PATH = Path("corpus/cuet/documents.clean.jsonl")
OUT_PATH = Path("scratch/eval_candidates.jsonl")

BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
CODE_RE = re.compile(r"\b[A-Z]{2,5}[\s-]?\d{3,4}\b")  # course-code-shaped tokens
NUMBER_RE = re.compile(r"\b\d{1,4}(?:\.\d+)?\b")

N_PER_CATEGORY = 6


def _chunk_to_dict(chunk) -> dict:
    return asdict(chunk) if is_dataclass(chunk) else dict(chunk)


def _load_all_chunks() -> list[dict]:
    """Re-chunks the whole corpus the same way check_corpus_chunks.py does,
    since chunks aren't persisted to disk anywhere — only documents are."""
    chunks: list[dict] = []
    with CORPUS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            doc = CleanDocument(**raw)  # see canonical_url caveat above if this errors
            for c in chunk_document(doc):
                chunks.append(_chunk_to_dict(c))
    return chunks


def _categorize(chunks: list[dict]) -> dict[str, list[dict]]:
    cats: dict[str, list[dict]] = {"bengali": [], "code_or_number": [], "prose": []}
    for c in chunks:
        text = c.get("text", "")
        if BENGALI_RE.search(text):
            cats["bengali"].append(c)
        elif CODE_RE.search(text) or NUMBER_RE.search(text):
            cats["code_or_number"].append(c)
        else:
            cats["prose"].append(c)
    return cats


def main() -> None:
    all_chunks = _load_all_chunks()
    print(f"Loaded {len(all_chunks)} chunks from {len(set(c['doc_id'] for c in all_chunks))} documents.\n")

    cats = _categorize(all_chunks)
    random.seed(42)  # reproducible sample across reruns

    candidates: list[dict] = []
    for label, pool in cats.items():
        sample = random.sample(pool, min(N_PER_CATEGORY, len(pool)))
        for c in sample:
            candidates.append({"category": label, **c})

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"Wrote {len(candidates)} candidates to {OUT_PATH}\n")
    print("=" * 70)
    for c in candidates:
        preview = c.get("text", "")[:220].replace("\n", " ")
        print(f"\n[{c['category']}] chunk_id={c.get('chunk_id')}  doc={c.get('title')}")
        print(f"  {preview}...")
    print("\n" + "=" * 70)
    print(
        "\nRead through these, pick ~15-20 across categories/languages, and write\n"
        "real queries for them into scratch/eval_queries.jsonl (see the example\n"
        "file for the format). Aim for a mix of:\n"
        "  - exact-term queries (course codes, numbers) -> tests sparse-style precision\n"
        "  - semantic/paraphrased queries -> tests dense understanding\n"
        "  - English queries AND Bengali queries, including cross-lingual\n"
        "    (English query -> Bengali-language chunk, or vice versa)"
    )


if __name__ == "__main__":
    main()