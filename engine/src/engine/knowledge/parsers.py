"""
Format-agnostic document parsing.

pdf.py holds the PDF engines (pymupdf / pdfplumber) since there's real
fallback logic between two libraries there. docx has one library, one
function, no engine choice — so it lives directly in this file instead
of a separate docx.py.

parse_document() is the single entry point documents.py should call.
It never needs to know file extensions or handle per-format errors —
that's all resolved here.
"""

import zipfile

from .pdf import (
    extract_pymupdf,
    extract_pdfplumber,
    extract_pdfplumber_positioned,
    has_real_tables,
    is_garbled,
    extract_ocr,
    lacks_common_words,
)

PDF_ENGINES = {
    "pymupdf": extract_pymupdf,
    "pdfplumber": extract_pdfplumber,
    "pdfplumber_positioned": extract_pdfplumber_positioned,
}


# is_garbled() and lacks_common_words() both deliberately punt (return
# False) on text shorter than their own thresholds — reasonable so they
# don't false-flag short legitimate documents, but it means anything
# under both thresholds slips past unchecked. That's exactly the gap a
# watermark-only text layer falls into (e.g. "CamScanner", 10 chars) —
# real text, non-garbled, but not real content. This floor catches it.
MIN_TRUSTED_CHARS = 30  # comfortably below the shortest real doc in the CUET corpus (334 chars)


def parse_pdf(path: str, engine: str = "auto") -> dict:
    if engine == "auto":
        engine = "pdfplumber_positioned" if has_real_tables(path) else "pymupdf"
    text, tables = PDF_ENGINES[engine](path)
    ocr_used = False
    # ...rest of the function is unchanged from here

    if (
        not text.strip()
        or len(text.strip()) < MIN_TRUSTED_CHARS
        or is_garbled(text)
        or lacks_common_words(text)
    ):
        text, tables = extract_ocr(path)
        ocr_used = True

    return {
        "text": text.strip(),
        "tables": tables,
        "empty": len(text.strip()) == 0,
        "ocr_used": ocr_used,
    }


def extract_docx(path: str) -> tuple[str, list]:
    # Imported here, not at module level, so importing parsers.py doesn't
    # hard-fail for anyone without python-docx installed — same convention
    # as fitz/pdfplumber inside the PDF engine functions.
    from docx import Document

    doc = Document(path)
    text_parts, tables = [], []

    # doc.paragraphs and doc.tables lose interleaving order on their own
    # (all paragraphs, then all tables) — walking the XML body directly
    # preserves document order.
    for element in doc.element.body:
        if element.tag.endswith('}p'):
            para = next(p for p in doc.paragraphs if p._p == element)
            if para.text.strip():
                text_parts.append(para.text)
        elif element.tag.endswith('}tbl'):
            table = next(t for t in doc.tables if t._tbl == element)
            tables.append([[cell.text.strip() for cell in row.cells] for row in table.rows])

    return "\n".join(text_parts), tables


def parse_docx(path: str) -> dict:
    text, tables = extract_docx(path)
    return {"text": text.strip(), "tables": tables, "empty": len(text.strip()) == 0}


def sniff_type(path: str) -> str | None:
    """Identify file type from content, for files with missing/untrustworthy
    extensions (common when crawling — e.g. download.php?id=123)."""
    with open(path, "rb") as f:
        header = f.read(4)

    if header == b"%PDF":
        return "pdf"

    if header == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(path) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass

    return None


def parse_document(path: str) -> dict:
    """Single entry point — dispatches by extension, falling back to
    content-sniffing when the extension is missing or untrustworthy."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else None
    file_type = ext if ext in ("pdf", "docx") else sniff_type(path)

    if file_type == "pdf":
        return parse_pdf(path)
    if file_type == "docx":
        return parse_docx(path)
    raise ValueError(f"Unsupported or unrecognized file type: {path}")


def ingest_batch(paths: list[str]) -> tuple[list[dict], list[dict]]:
    """Batch entry point for crawled files. A single malformed/unexpected
    file (dead-link HTML page, broken PDF, stray image with no extension)
    is expected at crawl scale — it's logged and skipped, not a hard
    failure that kills the rest of the batch."""
    results, skipped = [], []
    for path in paths:
        try:
            results.append(parse_document(path))
        except ValueError as e:
            skipped.append({"path": path, "reason": str(e)})
    return results, skipped