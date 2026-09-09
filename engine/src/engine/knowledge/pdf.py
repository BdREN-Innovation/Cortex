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