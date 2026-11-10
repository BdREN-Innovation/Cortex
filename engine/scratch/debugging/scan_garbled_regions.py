"""scratch/scan_garbled_regions.py

Whole-document checks (pdf.py's lacks_common_words, check_corpus_chunks.py's
looks_like_garbled_ocr) both average over the ENTIRE doc text. A document
mixing real English boilerplate (headers, "OFFICE ORDER", "Date:") with long
stretches of legacy-font-glyph garbage passes both gates, because the
boilerplate alone supplies enough common-word hits to clear the whole-doc
threshold — even though large sections are unusable.

This scans per-paragraph instead, so a garbled region can't hide behind a
clean region elsewhere in the same document.

Usage:
    uv run python -m scratch.scan_garbled_regions
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CORPUS_PATH = Path("corpus/cuet/documents.jsonl")

_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
_WORD_RE = re.compile(r"[a-zA-Z]{2,}")
_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
_BENGALI_BLEED_MAX_FRACTION = 0.5  # above this: coherent Bengali content, exempt.
                                     # below this (but >0): scattered bleed — corruption signal.

# Same list as pdf.py's _COMMON_ENGLISH_WORDS, kept identical on purpose so
# results are comparable to the existing whole-doc gate.
_COMMON_ENGLISH_WORDS = frozenset({
    "the", "and", "of", "to", "a", "in", "is", "for", "on", "that",
    "with", "as", "are", "this", "by", "or", "be", "at", "from", "an",
})

MIN_WORDS_PER_PARAGRAPH = 8  # below this, too short to judge reliably


def paragraph_is_garbled(
    text: str,
    min_garbled_windows: int = 3,
    min_garbled_ratio: float = 0.2,
) -> bool:
    """Windowed check — same fix as pdf.py's has_garbled_paragraph(). The
    original blank-line split (r"\n\s*\n") assumed paragraph breaks that
    don't exist in this corpus's extracted text (pymupdf/OCR both join with
    a single \n), which silently collapsed every single-page document into
    one giant "paragraph" and made this scanner just as blind as the
    whole-document check it was meant to catch.

    Second bug (fixed): the Bengali-script exemption previously ran against
    " ".join(window), but `window` is built via _WORD_RE.findall() (ASCII
    letters only) — so it can never contain Bengali characters, and the
    exemption was dead code. Fixed by testing the raw source lines feeding
    the window instead.

    Third bug (this change): originally returned True the moment ANY single
    window failed the common-word check. That's too strict — a dense course
    table (course codes, credit numbers, no prose) can fail one window on
    its own even though the document is completely legitimate. Confirmed via
    the CUET MME syllabus doc (de1bedf54e5542dd): its old documents.jsonl
    extraction was clean, but one table window tripped this check, the
    document got needlessly sent through OCR, and OCR genuinely garbled it.
    Now requires both a minimum count and a minimum fraction of all judged
    windows to be bad before flagging the whole paragraph — a real garbled
    document fails most/all of its windows; an isolated bad table window
    does not.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    window: list[str] = []
    window_lines: list[str] = []
    total_windows = 0
    garbled_windows = 0

    for line in lines:
        window.extend(_WORD_RE.findall(line))
        window_lines.append(line)
        if len(window) >= MIN_WORDS_PER_PARAGRAPH:
            total_windows += 1
            joined = " ".join(window_lines)
            non_space = joined.replace(" ", "")
            bengali_chars = _BENGALI_RE.findall(joined)
            bengali_fraction = len(bengali_chars) / len(non_space) if non_space else 0.0
            if 0 < bengali_fraction <= _BENGALI_BLEED_MAX_FRACTION:
                hits = sum(1 for w in window if w.lower() in _COMMON_ENGLISH_WORDS)
                if hits == 0:
                    garbled_windows += 1
            window = []
            window_lines = []

        # Require a minimum number of judgeable windows before trusting the
    # ratio at all — otherwise a 1- or 2-window document only needs a
    # single bad window to hit 100%, which collapses back to the old
    # "any one bad window flags the doc" behavior this fix was meant to
    # replace. Same conservative "not enough evidence, don't judge" pattern
    # lacks_common_words() already uses for short documents.
    if total_windows < min_garbled_windows:
        return False

    return (garbled_windows / total_windows) >= min_garbled_ratio

def main() -> None:
    total_docs = 0
    docs_with_any_garbled_paragraph = 0
    total_paragraphs = 0
    total_garbled_paragraphs = 0
    worst_docs: list[tuple[float, str, str, int, int]] = []  # (ratio, doc_id, title, garbled, total)

    with CORPUS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            text = doc.get("text", "")
            paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
            if not paragraphs:
                continue

            total_docs += 1
            judged = [p for p in paragraphs if len(_WORD_RE.findall(p)) >= MIN_WORDS_PER_PARAGRAPH]
            if not judged:
                continue  # nothing long enough in this doc to judge

            garbled = [p for p in judged if paragraph_is_garbled(p)]
            total_paragraphs += len(judged)
            total_garbled_paragraphs += len(garbled)

            if garbled:
                docs_with_any_garbled_paragraph += 1
                ratio = len(garbled) / len(judged)
                worst_docs.append((ratio, doc.get("doc_id", "?"), doc.get("title", ""), len(garbled), len(judged)))

    worst_docs.sort(reverse=True)

    print(f"Documents scanned:              {total_docs}")
    print(f"Judgeable paragraphs total:      {total_paragraphs}")
    print(f"Garbled paragraphs total:        {total_garbled_paragraphs}")
    print(f"Docs with >=1 garbled paragraph: {docs_with_any_garbled_paragraph} ({docs_with_any_garbled_paragraph/total_docs:.1%} of corpus)")
    print()
    print("Worst offenders (by fraction of paragraphs garbled):")
    print("-" * 70)
    for ratio, doc_id, title, n_garbled, n_judged in worst_docs[:20]:
        print(f"  {ratio:.0%}  ({n_garbled}/{n_judged})  {doc_id}  {title}")


if __name__ == "__main__":
    main()