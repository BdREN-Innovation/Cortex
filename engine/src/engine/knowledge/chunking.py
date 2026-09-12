"""Documents -> chunks.

A chunk is the unit that gets embedded, retrieved and shown to the model. How
you cut them decides more about answer quality than almost anything else you
will choose.

TEAM B OWNS THIS FILE.

Decisions you own
-----------------
This file has more genuinely open questions than anything else in the pipeline,
and it matters more than your embedding model. Decide these deliberately, and
be able to defend them with Team C's numbers.

* Where do you split? Sentences, paragraphs, headings, a fixed character count?
  A split mid-sentence produces a chunk that means nothing on its own.
* How big is a chunk? Too small and an answer straddles two of them so neither
  scores well; too large and the one relevant sentence is diluted.
* Do chunks overlap? By how much? Overlap catches straddling answers and costs
  you index size and embedding spend.
* Do you count tokens properly or approximate from characters? A real tokenizer
  is exact and adds a dependency; a ratio is close enough for deciding where to
  cut. Which do you actually need?
* What happens to a document shorter than one chunk? To a trailing fragment of
  four words?
* A markdown table is in the text. Splitting one down the middle produces two
  useless halves — does your splitter know that?

"""


from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from engine.contracts.documents import Chunk, CleanDocument


@dataclass
class ChunkConfig:
    target_tokens: int = 350
    overlap_tokens: int = 60
    min_tokens: int = 40


# No tokenizer library in the project (see parsers.py's own note on this).
# chars/4 is the standard rough English-text approximation; good enough for
# deciding *where* to cut, not for exact billing. Revisit against Team C's
# golden set if retrieval quality suggests chunk sizes are consistently off.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


_TABLE_BLOCK_RE = re.compile(r"(?:^\|.*\|$\n?)+", re.MULTILINE)


def _protected_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of markdown table blocks — never split through
    these. Docs from pymupdf have no tables; docs from
    pdfplumber_positioned render tables as inline |...| markdown."""
    return [m.span() for m in _TABLE_BLOCK_RE.finditer(text)]


def _split_paragraphs(text: str) -> list[tuple[int, int]]:
    """Blank-line-separated spans, with table blocks carved out as their
    own atomic paragraph even when flush against adjacent text."""
    protected = _protected_spans(text)
    spans = []
    pos = 0
    for m in re.finditer(r"\n\s*\n", text):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))

    final_spans = []
    for start, end in spans:
        overlapping = [(ts, te) for ts, te in protected if ts < end and te > start]
        if not overlapping:
            final_spans.append((start, end))
            continue
        cursor = start
        for ts, te in sorted(overlapping):
            if ts > cursor:
                final_spans.append((cursor, ts))
            final_spans.append((max(ts, start), min(te, end)))
            cursor = te
        if cursor < end:
            final_spans.append((cursor, end))

    return [(s, e) for s, e in final_spans if text[s:e].strip()]

def _is_table_text(text: str) -> bool:
    lines = [l for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return False
    return sum(1 for l in lines if l.strip().startswith("|")) / len(lines) > 0.8


def _split_table_rows(text: str, start_offset: int, config: ChunkConfig) -> list[tuple[int, int]]:
    chunks = []
    cur_start = None
    cur_end = None
    cur_tokens = 0
    pos = 0
    for line in text.splitlines(keepends=True):
        s, e = pos, pos + len(line)
        pos = e
        if not line.strip():
            continue
        row_tokens = estimate_tokens(line)
        if cur_start is not None and cur_tokens + row_tokens > config.target_tokens:
            chunks.append((start_offset + cur_start, start_offset + cur_end))
            cur_start = None
            cur_tokens = 0
        if cur_start is None:
            cur_start = s
        cur_end = e
        cur_tokens += row_tokens
    if cur_start is not None:
        chunks.append((start_offset + cur_start, start_offset + cur_end))
    return chunks

def _split_oversized(text: str, start_offset: int, config: ChunkConfig) -> list[tuple[int, int]]:
    """Fallback for a single paragraph that alone exceeds target_tokens
    (a huge table, or a genuinely long paragraph). Splits on sentence
    boundaries where possible; falls back to a raw char cut only if a
    'sentence' itself is still oversized (e.g. a table block)."""
    if _is_table_text(text):
      return _split_table_rows(text, start_offset, config)
    sentences = [(m.start(), m.end()) for m in re.finditer(r"[^.!?\n]+[.!?]?\s*", text)] or [(0, len(text))]
    spans = []
    cur_start = 0
    cur_tokens = 0
    for s_start, s_end in sentences:
        seg_tokens = estimate_tokens(text[s_start:s_end])
        if cur_tokens and cur_tokens + seg_tokens > config.target_tokens:
            spans.append((cur_start, s_start))
            cur_start = s_start
            cur_tokens = 0
        cur_tokens += seg_tokens
    spans.append((cur_start, len(text)))

    # Raw char fallback for any span still oversized (single giant "sentence")
    out = []
    for s, e in spans:
        if estimate_tokens(text[s:e]) <= config.target_tokens * 1.5 or e - s < 200:
            out.append((s, e))
            continue
        step_chars = config.target_tokens * _CHARS_PER_TOKEN
        i = s
        while i < e:
            j = min(i + step_chars, e)
            out.append((i, j))
            i = j
    return [(start_offset + s, start_offset + e) for s, e in out]


def _pack_paragraphs(text: str, paragraphs: list[tuple[int, int]], config: ChunkConfig) -> list[tuple[int, int]]:
    """Packs paragraphs up to target_tokens, splitting only the paragraphs
    that alone exceed it. Adjacent chunks overlap by pulling trailing
    paragraphs from the previous chunk forward, up to overlap_tokens."""
    atomic: list[tuple[int, int]] = []
    for p_start, p_end in paragraphs:
        p_tokens = estimate_tokens(text[p_start:p_end])
        if p_tokens > config.target_tokens:
            atomic.extend(_split_oversized(text[p_start:p_end], p_start, config))
        else:
            atomic.append((p_start, p_end))

        chunks: list[tuple[int, int]] = []
    i = 0
    n = len(atomic)
    prev_max_atom_idx = -1  # last atom index included in the previously emitted chunk
    while i < n:
        cur_start = atomic[i][0]
        cur_end = atomic[i][1]
        cur_tokens = estimate_tokens(text[cur_start:cur_end])
        j = i + 1
        while j < n:
            seg_tokens = estimate_tokens(text[atomic[j][0]:atomic[j][1]])
            if cur_tokens + seg_tokens > config.target_tokens:
                break
            cur_end = atomic[j][1]
            cur_tokens += seg_tokens
            j += 1

        # Guard against a chunk that is pure overlap - every atom in it was
        # already included in the previous chunk, making it a literal
        # substring of its neighbor. Force in the next atom so it always
        # contributes new content, even past target_tokens.
        if j - 1 <= prev_max_atom_idx and j < n:
            cur_end = atomic[j][1]
            cur_tokens += estimate_tokens(text[atomic[j][0]:atomic[j][1]])
            j += 1

        chunks.append((cur_start, cur_end))
        prev_max_atom_idx = j - 1

        if j >= n:
            break

        # Overlap: walk backward from j to find how many trailing atomic
        # spans from this chunk fit within overlap_tokens, and resume from
        # there instead of j, so the next chunk repeats that tail.
        if cur_tokens <= config.overlap_tokens:
            i = j
            continue

        back = j - 1
        overlap_tok = 0
        while back > i:
            seg_tokens = estimate_tokens(text[atomic[back][0]:atomic[back][1]])
            if overlap_tok + seg_tokens > config.overlap_tokens:
                break
            overlap_tok += seg_tokens
            back -= 1
        i = max(back + 1, i + 1)  # always make progress

    return chunks


def _chunk_id(doc_id: str, ordinal: int) -> str:
    """Stable across re-indexing runs: derived only from doc_id + position,
    never from wall-clock time or run-specific state."""
    return hashlib.sha256(f"{doc_id}:{ordinal}".encode("utf-8")).hexdigest()[:16]


def chunk_document(doc: CleanDocument, config: ChunkConfig | None = None) -> list[Chunk]:
    config = config or ChunkConfig()
    text = doc.text

    if not text.strip():
        return []

    if estimate_tokens(text) <= config.target_tokens:
        spans = [(0, len(text))]
    else:
        paragraphs = _split_paragraphs(text)
        spans = _pack_paragraphs(text, paragraphs, config)

    # Merge a trailing fragment under min_tokens into the previous chunk
    # rather than shipping a near-empty chunk that can't score well on its own.
        # Merge any chunk under min_tokens into a neighbor, rather than shipping
    # near-empty chunks that can't score well on their own. Prefer merging
    # into the previous chunk; if the very first chunk is undersized (no
    # previous chunk to absorb it into), merge it forward instead.
    if len(spans) > 1:
        merged: list[tuple[int, int]] = [spans[0]]
        for start, end in spans[1:]:
            if estimate_tokens(text[start:end]) < config.min_tokens:
                prev_start, prev_end = merged[-1]
                merged[-1] = (prev_start, end)
            else:
                merged.append((start, end))
        if len(merged) > 1 and estimate_tokens(text[merged[0][0]:merged[0][1]]) < config.min_tokens:
            second_start, second_end = merged[1]
            merged = [(merged[0][0], second_end)] + merged[2:]
        spans = merged

    chunks = []
    for ordinal, (start, end) in enumerate(spans):
        chunk_text = text[start:end].strip()
        if not chunk_text:
            continue
        chunks.append(Chunk(
            chunk_id=_chunk_id(doc.doc_id, ordinal),
            doc_id=doc.doc_id,
            text=chunk_text,
            ordinal=ordinal,
            canonical_url=doc.canonical_url,
            title=doc.title,
            section_path=doc.section_path,
            token_estimate=estimate_tokens(chunk_text),
        ))
    return chunks


def chunk_documents(docs: list[CleanDocument], config: ChunkConfig | None = None) -> list[Chunk]:
    out: list[Chunk] = []
    for doc in docs:
        out.extend(chunk_document(doc, config))
    return out