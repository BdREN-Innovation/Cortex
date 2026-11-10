"""Independent of scan_garbled_regions.py's current state — reproduces the
original 'zero common-word hits' trigger directly, so we can inspect what
the 17 pure-ASCII false positives actually contained, even after the
Bengali-fraction patch has already been applied and would otherwise hide
them from paragraph_is_garbled()."""
import json
import re
from pathlib import Path

_WORD_RE = re.compile(r"[a-zA-Z]{2,}")
_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")
_COMMON_ENGLISH_WORDS = frozenset({
    "the", "and", "of", "to", "a", "in", "is", "for", "on", "that",
    "with", "as", "are", "this", "by", "or", "be", "at", "from", "an",
})
MIN_WORDS_PER_PARAGRAPH = 8
CORPUS_PATH = Path("corpus/cuet/documents.clean.jsonl")


def zero_common_word_windows(text: str) -> list[str]:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    window: list[str] = []
    window_lines: list[str] = []
    bad: list[str] = []
    for line in lines:
        window.extend(_WORD_RE.findall(line))
        window_lines.append(line)
        if len(window) >= MIN_WORDS_PER_PARAGRAPH:
            hits = sum(1 for w in window if w.lower() in _COMMON_ENGLISH_WORDS)
            if hits == 0:
                bad.append(" ".join(window_lines))
            window = []
            window_lines = []
    return bad


with CORPUS_PATH.open(encoding="utf-8") as f:
    for line in f:
        doc = json.loads(line)
        text = doc.get("text", "")
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        judged = [p for p in paragraphs if len(_WORD_RE.findall(p)) >= MIN_WORDS_PER_PARAGRAPH]
        for p in judged:
            for w in zero_common_word_windows(p):
                if not _BENGALI_RE.search(w):  # pure ASCII, no bleed — the 17-type case
                    print(f"=== {doc.get('doc_id')} ===")
                    print(repr(w[:300]))
                    print()