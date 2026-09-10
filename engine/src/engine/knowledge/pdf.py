import re
from engine.knowledge.extraction import rows_to_markdown

def extract_pymupdf(path: str) -> tuple[str, list]:
    import fitz
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    return text, []


def extract_pdfplumber(path: str) -> tuple[str, list]:
    import pdfplumber
    text_parts, tables = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
            tables.extend(t for t in page.extract_tables() if t)
    return "\n".join(text_parts), tables

def _is_real_table(table: list[list]) -> bool:
    """False-positive filter for pdfplumber's extract_tables(). Validated
    against the CUET corpus's syllabus PDFs — see scratch/diagnose_tables.py.
    Drops: single-column mis-detections (numbered lists, reference blocks)
    and the recurring 'COURSE CONTENT / No. of Lectures' 2x2 section-header
    noise that pdfplumber's line-based strategy latches onto on nearly every
    content page of these documents."""
    if not table:
        return False

    n_rows = len(table)
    n_cols = max(len(r) for r in table)

    if n_cols < 2:
        return False

    flat_lower = {str(c).strip().lower() for row in table for c in row if c}
    if n_rows == 2 and n_cols == 2 and "course content" in flat_lower:
        return False

    total_cells = n_rows * n_cols
    non_empty = sum(1 for row in table for c in row if c and str(c).strip())
    if total_cells and (non_empty / total_cells) < 0.5:
        return False

    return True


def has_real_tables(path: str) -> bool:
    """Quick yes/no: does this PDF contain at least one real (filtered) table?
    Used by parse_pdf's 'auto' engine selection to decide pymupdf vs
    pdfplumber_positioned per doc, without needing a hardcoded doc list.
    Short-circuits on the first real table found."""
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            found = page.find_tables()
            if any(_is_real_table(t.extract()) for t in found):
                return True
    return False


def extract_pdfplumber_positioned(path: str) -> tuple[str, list]:
    """Text + tables extraction that keeps tables anchored in reading order,
    so a table's markdown sits inline in `text` exactly where it visually
    appears on the page.

    Works at the word level rather than cropping/outside_bbox: each word
    keeps its own bounding box from extract_words(), words falling inside a
    real table's bbox are excluded from the prose stream, and the remaining
    words are regrouped into lines by vertical position. This avoids the
    word-mashing and reading-order bugs that outside_bbox() + extract_text()
    produced (cropping disconnected regions breaks pdfplumber's space
    inference and collapses multi-line surrounding text into one blob).
    """
    import pdfplumber

    text_parts: list[str] = []
    all_tables: list[list] = []
    LINE_TOLERANCE = 3  # px — words within this vertical band count as one line

    def _word_in_bbox(word: dict, bbox: tuple[float, float, float, float]) -> bool:
        x0, top, x1, bottom = bbox
        cx = (word["x0"] + word["x1"]) / 2
        cy = (word["top"] + word["bottom"]) / 2
        return x0 <= cx <= x1 and top <= cy <= bottom

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            found = page.find_tables()
            real_tables = [t for t in found if _is_real_table(t.extract())]

            if not real_tables:
                text_parts.append(page.extract_text() or "")
                continue

            table_bboxes = [t.bbox for t in real_tables]
            words = page.extract_words(x_tolerance=2)
            outside_words = [
                w for w in words
                if not any(_word_in_bbox(w, bbox) for bbox in table_bboxes)
            ]
            outside_words.sort(key=lambda w: (w["top"], w["x0"]))

            # Group words into lines by vertical proximity.
            lines: list[list[dict]] = []
            current_line: list[dict] = []
            current_top: float | None = None
            for w in outside_words:
                if current_top is None or abs(w["top"] - current_top) <= LINE_TOLERANCE:
                    current_line.append(w)
                    current_top = current_top if current_top is not None else w["top"]
                else:
                    lines.append(current_line)
                    current_line = [w]
                    current_top = w["top"]
            if current_line:
                lines.append(current_line)

            # Each line and each table becomes a positioned block, so they
            # interleave correctly regardless of how many text runs sit
            # before/after/between tables on the page.
            blocks: list[tuple[float, str, object]] = []
            for line in lines:
                line_sorted = sorted(line, key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in line_sorted)
                blocks.append((min(w["top"] for w in line), "text", text))
            for t in real_tables:
                blocks.append((t.bbox[1], "table", t))
            blocks.sort(key=lambda b: b[0])

            page_parts = []
            for _, kind, content in blocks:
                if kind == "table":
                    rows = content.extract()
                    page_parts.append(rows_to_markdown(rows))
                    all_tables.append(rows)
                else:
                    page_parts.append(content)
            text_parts.append("\n".join(page_parts))

    return "\n".join(text_parts), all_tables


# Characters expected in valid text: Bangla Unicode block, Latin letters,
# digits, common punctuation/whitespace. Catches genuinely non-Unicode byte
# soup / mojibake outside the printable range. Does NOT catch legacy-font
# glyph remapping where the "garbage" is composed entirely of plain ASCII
# letters — see lacks_common_words() below for that case.
_VALID_CHARS = re.compile(r'[\u0980-\u09FF a-zA-Z0-9.,;:!?()\-\'"\n\t]')


def is_garbled(text: str, min_length: int = 50) -> bool:
    stripped = text.strip()
    if len(stripped) < min_length:
        return False
    valid_ratio = len(_VALID_CHARS.findall(stripped)) / len(stripped)
    return valid_ratio < 0.6  # untuned — see note below


# Common short English words. Real English prose of any real length reliably
# contains several of these. Kept deliberately small/high-frequency so we
# aren't relying on obscure words a short legit document might not use.
_COMMON_ENGLISH_WORDS = frozenset({
    "the", "and", "of", "to", "a", "in", "is", "for", "on", "that",
    "with", "as", "are", "this", "by", "or", "be", "at", "from", "an",
})

_WORD_RE = re.compile(r"[a-zA-Z]{2,}")


def lacks_common_words(text: str, min_words: int = 20) -> bool:
    """Catches the specific failure mode font checks and is_garbled() both
    miss: a PDF whose font is declared as an ordinary font (e.g. 'Helvetica')
    but is actually re-encoded via a custom /Differences array to render
    Bangla glyphs. get_fonts() shows nothing suspicious (base font name is
    boring), and the resulting "text" is composed entirely of plain ASCII
    letters/punctuation — so is_garbled()'s character-class ratio scores it
    as valid too. It just never forms real English words, because letter
    placement is driven by Bangla glyph shapes, not English spelling.

    Untuned like is_garbled — min_words=20 is a guess at a threshold high
    enough to avoid false-flagging short legitimate documents (e.g. a table
    of numbers) that might not happen to contain any of these words.
    """
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if len(words) < min_words:
        return False  # not enough Latin-alpha content to judge reliably
    hits = sum(1 for w in words if w in _COMMON_ENGLISH_WORDS)
    return hits == 0


def extract_ocr(path: str, lang: str = "ben+eng", dpi: int = 300) -> tuple[str, list]:
    """Renders each page to an image via fitz (already a pdf.py dependency)
    and runs Tesseract. No text-layer trust involved, so font encoding
    tricks are irrelevant here. Tables aren't recovered — OCR gives you
    a flat text blob, not table structure."""
    import io
    import os
    import fitz
    import pytesseract
    from PIL import Image

    if os.name == "nt":
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    doc = fitz.open(path)
    matrix = fitz.Matrix(dpi / 72, dpi / 72)  # fitz default render is 72 DPI
    text_parts = []

    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text_parts.append(pytesseract.image_to_string(img, lang=lang))

    return "\n".join(text_parts), []