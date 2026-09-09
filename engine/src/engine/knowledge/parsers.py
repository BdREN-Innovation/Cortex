from .pdf import extract_pymupdf, extract_pdfplumber

ENGINES = {"pymupdf": extract_pymupdf, "pdfplumber": extract_pdfplumber}

def parse_pdf(path: str, engine: str = "pymupdf") -> dict:
    text, tables = ENGINES[engine](path)
    return {"text": text.strip(), "tables": tables, "empty": len(text.strip()) == 0}