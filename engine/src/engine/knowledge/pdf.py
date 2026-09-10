import re

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