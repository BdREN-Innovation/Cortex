"""
Corpus-wide chunking sanity checker.

Loads already-extracted documents (documents.clean.jsonl, falling back to
documents.jsonl) from every corpus under a root directory, runs them through
chunk_document, and flags any document whose chunks violate an invariant:

  1. No chunk boundary cuts a markdown table row in half.
  2. No chunk is under config.min_tokens (except a single-chunk doc).
  3. No chunk's full text is a substring of an adjacent chunk's text.
  4. No chunk is wildly oversized (> 1.75x target_tokens).
  5. Basic sanity: non-empty text, sequential ordinals, chunk text is a
     verbatim substring of the source doc text.
  6. Garbled-OCR heuristic: flag docs whose text looks like OCR mojibake
     (very low ratio of common English words to word-like tokens, and no
     real Bengali script present) so they don't silently chunk
     "successfully" while useless.

The JSONL records come from scratch.contracts_stub.CleanDocument (extraction
stage), which has different fields than engine.contracts.documents.CleanDocument
(chunking stage). This script bridges the two by introspecting the chunking
CleanDocument's dataclass fields at runtime, so it doesn't hardcode a schema
that might drift.

Usage:
    uv run python -m scratch.check_corpus [corpus_root]

Defaults to "corpus" if no root is given.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sys
from pathlib import Path

from engine.knowledge.chunking import chunk_document, ChunkConfig
from engine.contracts.documents import CleanDocument as ChunkingCleanDocument

DOC_FILENAMES = ["documents.clean.jsonl", "documents.jsonl"]


def find_doc_files(root: Path) -> list[Path]:
    """One file per corpus subdirectory - prefer documents.clean.jsonl."""
    found = []
    for corpus_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for name in DOC_FILENAMES:
            candidate = corpus_dir / name
            if candidate.exists():
                found.append(candidate)
                break
    # Also check the root itself, in case it IS a single corpus dir.
    for name in DOC_FILENAMES:
        candidate = root / name
        if candidate.exists() and candidate not in found:
            found.append(candidate)
            break
    return found


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_chunking_doc(record: dict) -> ChunkingCleanDocument:
    """Map an extraction-stage JSONL record onto whatever fields
    engine.contracts.documents.CleanDocument actually declares, without
    hardcoding its schema."""
    field_names = {f.name for f in dataclasses.fields(ChunkingCleanDocument)}
    text = record.get("text", "")
    url = record.get("url", "")

    candidates = {
        "doc_id": record.get("doc_id"),
        "source_url": url,
        "canonical_url": url,
        "url": url,
        "title": record.get("title", ""),
        "text": text,
        "section_path": record.get("section_path", []),
        "tables": record.get("tables", []),
        "source_path": record.get("source_path", ""),
        "meta": record.get("meta", {}),
        "content_hash": _content_hash(text),
        "fetched_at": "2026-09-11T00:00:00Z",
        "doc_type": record.get("doc_type", ""),
    }

    kwargs = {k: v for k, v in candidates.items() if k in field_names}

    missing = field_names - kwargs.keys()
    required_missing = [
        f.name for f in dataclasses.fields(ChunkingCleanDocument)
        if f.name in missing
        and f.default is dataclasses.MISSING
        and f.default_factory is dataclasses.MISSING
    ]
    if required_missing:
        raise ValueError(
            f"CleanDocument requires fields not in our mapping: {required_missing}. "
            f"Update build_chunking_doc() in check_corpus.py to supply them."
        )

    return ChunkingCleanDocument(**kwargs)


# --- OCR mojibake heuristic ---------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")

# A handful of very common English function words. Garbled OCR text tends
# to produce word-shaped tokens that never hit this list.
_COMMON_EN = {
    "the", "and", "for", "with", "this", "that", "from", "have", "will",
    "are", "was", "not", "all", "you", "your", "engineering", "university",
}


def looks_like_garbled_ocr(text: str, meta: dict) -> bool:
    if not meta.get("ocr_used"):
        return False
    if _BENGALI_RE.search(text):
        # Has real Bengali script present - not the mojibake failure mode
        # we're detecting (garbled OCR here shows up as fake-Latin noise).
        return False
    words = _WORD_RE.findall(text.lower())
    if len(words) < 20:
        return False  # too short to judge
    common_hits = sum(1 for w in words if w in _COMMON_EN)
    ratio = common_hits / len(words)
    return ratio < 0.03  # real English text clears this easily


# --- chunk-level checks ---------------------------------------------------

def check_table_row_integrity(chunks) -> list[str]:
    """Only flags a malformed table row if it sits at the very start or
    end of a chunk's text - those are the only positions a chunk boundary
    could actually have caused. A malformed row in the middle of a chunk
    was already broken in the source markdown before chunking touched it,
    so it's not a chunking bug and shouldn't be reported as one."""
    issues = []
    for c in chunks:
        lines = [l.strip() for l in c.text.split("\n") if l.strip()]
        if not lines:
            continue
        boundary_lines = {lines[0], lines[-1]}  # dedupes the 1-line-chunk case
        for stripped in boundary_lines:
            if "|" not in stripped:
                continue
            if stripped.startswith("|") and not stripped.endswith("|"):
                issues.append(f"chunk {c.ordinal}: table row looks cut off at boundary: {stripped[:80]!r}")
    return issues


def check_min_tokens(chunks, config: ChunkConfig) -> list[str]:
    if len(chunks) <= 1:
        return []
    return [
        f"chunk {c.ordinal}: undersized ({c.token_estimate} tokens < min {config.min_tokens})"
        for c in chunks if c.token_estimate < config.min_tokens
    ]


def check_adjacent_duplicates(chunks) -> list[str]:
    issues = []
    for i in range(len(chunks) - 1):
        a, b = chunks[i].text.strip(), chunks[i + 1].text.strip()
        if a and b and (a in b or b in a):
            issues.append(f"chunks {chunks[i].ordinal}/{chunks[i+1].ordinal}: one is a substring of the other")
    return issues


def check_oversized(chunks, config: ChunkConfig) -> list[str]:
    limit = config.target_tokens * 1.75
    return [
        f"chunk {c.ordinal}: oversized ({c.token_estimate} tokens > {limit:.0f} limit)"
        for c in chunks if c.token_estimate > limit
    ]


def check_basic_sanity(chunks, doc_text: str) -> list[str]:
    issues = []
    for i, c in enumerate(chunks):
        if c.ordinal != i:
            issues.append(f"chunk at position {i} has ordinal {c.ordinal} (expected {i})")
        if not c.text.strip():
            issues.append(f"chunk {c.ordinal}: empty text")
        elif c.text not in doc_text:
            issues.append(f"chunk {c.ordinal}: text not found verbatim in source doc (offset drift?)")
    return issues


def check_document(record: dict, config: ChunkConfig) -> tuple[bool, list[str], int]:
    try:
        doc = build_chunking_doc(record)
        chunks = chunk_document(doc, config)
    except Exception as e:
        return False, [f"CRASHED during chunking: {e!r}"], 0

    issues = []
    if looks_like_garbled_ocr(record.get("text", ""), record.get("meta", {})):
        issues.append("text looks like garbled/mojibake OCR output (low common-word ratio)")
    issues += check_basic_sanity(chunks, doc.text)
    issues += check_table_row_integrity(chunks)
    issues += check_min_tokens(chunks, config)
    issues += check_adjacent_duplicates(chunks)
    issues += check_oversized(chunks, config)
    return True, issues, len(chunks)


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("corpus")
    if not root.exists():
        print(f"Corpus root not found: {root}")
        sys.exit(1)

    doc_files = find_doc_files(root)
    print(f"Found {len(doc_files)} documents.jsonl file(s) under {root}")
    for f in doc_files:
        print(f"  {f}")
    print()

    config = ChunkConfig()
    clean_count = flagged_count = crashed_count = ocr_flagged = 0
    total_docs = total_chunks = 0

    for doc_file in doc_files:
        with doc_file.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"[BAD JSON] {doc_file}:{line_no}: {e}")
                    crashed_count += 1
                    continue

                total_docs += 1
                ok, issues, n_chunks = check_document(record, config)
                total_chunks += n_chunks
                label = record.get("doc_id", f"{doc_file}:{line_no}")

                if not ok:
                    crashed_count += 1
                    print(f"[CRASH] {label} ({record.get('title', '')})")
                    for issue in issues:
                        print(f"    {issue}")
                    print()
                elif issues:
                    flagged_count += 1
                    if any("garbled" in i for i in issues):
                        ocr_flagged += 1
                    print(f"[FLAGGED] {label} ({record.get('title', '')}) - {n_chunks} chunks")
                    for issue in issues:
                        print(f"    {issue}")
                    print()
                else:
                    clean_count += 1

    print("=" * 60)
    print(f"Checked {total_docs} documents, {total_chunks} total chunks")
    print(f"  clean:        {clean_count}")
    print(f"  flagged:      {flagged_count}  (of which garbled-OCR: {ocr_flagged})")
    print(f"  crashed:      {crashed_count}")


if __name__ == "__main__":
    main()