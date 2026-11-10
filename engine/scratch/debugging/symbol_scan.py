"""Broader symbol scan: for every zero-common-word window in the corpus,
independent of the current has_garbled_paragraph()/paragraph_is_garbled()
logic, bucket every non-ASCII-alnum, non-whitespace character that isn't
already explained by the existing fixes (@/%/(r), Bengali U+0980-U+09FF).
Goal: surface a 4th corruption mode before it silently slips past the
suspect-char patch the same way the signature-block noise did."""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

_WORD_RE = re.compile(r"[a-zA-Z]{2,}")
_COMMON_ENGLISH_WORDS = frozenset({
    "the", "and", "of", "to", "a", "in", "is", "for", "on", "that",
    "with", "as", "are", "this", "by", "or", "be", "at", "from", "an",
})
MIN_WORDS_PER_PARAGRAPH = 8
CORPUS_PATH = Path("corpus/cuet/documents.clean.jsonl")

_KNOWN_SUSPECT = re.compile(r"[@%®]")
_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")


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


char_counter: Counter = Counter()
example_by_char: dict[str, tuple[str, str]] = {}

with CORPUS_PATH.open(encoding="utf-8") as f:
    for line in f:
        doc = json.loads(line)
        text = doc.get("text", "")
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        judged = [p for p in paragraphs if len(_WORD_RE.findall(p)) >= MIN_WORDS_PER_PARAGRAPH]
        for p in judged:
            for w in zero_common_word_windows(p):
                for ch in w:
                    if ch.isascii() and (ch.isalnum() or ch.isspace()):
                        continue
                    if ch.isspace():
                        continue
                    if _KNOWN_SUSPECT.match(ch) or _BENGALI_RE.match(ch):
                        continue
                    char_counter[ch] += 1
                    if ch not in example_by_char:
                        example_by_char[ch] = (doc.get("doc_id"), w[:150])

for ch, count in char_counter.most_common(50):
    name = unicodedata.name(ch, "UNKNOWN")
    cat = unicodedata.category(ch)
    doc_id, example = example_by_char[ch]
    print(f"{ch!r}  U+{ord(ch):04X}  {name}  cat={cat}  count={count}  doc={doc_id}")
    print(f"    e.g. {example!r}")