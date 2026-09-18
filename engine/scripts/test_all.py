# test_all.py — manual check script (not pytest, no asserts, meant to be eyeballed)
#
# Covers PDF + docx together via parse_document() (same {"text","tables","empty"}
# shape, both go through parsers.py). HTML gets a small local adapter because
# extract() takes an HTML string + url, not a file path, and returns a different
# shape (Extracted dataclass) — that mismatch is real (HTML arrives from the
# crawler in memory in production, never as a file), so the adapter stays here
# rather than being pushed into parsers.py.

from pathlib import Path
from engine.knowledge.parsers import parse_document
from engine.knowledge.extraction import extract

FIXTURES_DIR = Path("fixtures/site/docs")


def parse_html(path: Path) -> dict:
    html = path.read_text(encoding="utf-8")
    result = extract(html, url=f"file://{path}")
    return {
        "text": result.text,
        "tables": [t["markdown"] for t in result.tables],
        "empty": len(result.text.strip()) == 0,
    }


def parse_any(path: Path) -> dict:
    if path.suffix.lower() in (".html", ".htm"):
        return parse_html(path)
    return parse_document(str(path))


def main() -> None:
    results, skipped = [], []

    for path in sorted(FIXTURES_DIR.iterdir()):
        if path.is_dir():
            continue
        try:
            results.append((path, parse_any(path)))
        except ValueError as e:
            skipped.append({"path": str(path), "reason": str(e)})

    print(f"parsed: {len(results)}, skipped: {len(skipped)}\n")

    for path, result in results:
        print(f"--- {path.name} ---")
        # .get() rather than [] here — only parse_pdf's return dict has
        # 'ocr_used'; docx and html results don't, so this prints "None"
        # for those instead of blowing up with a KeyError.
        print(
            f"empty: {result['empty']}, chars: {len(result['text'])}, "
            f"tables: {len(result['tables'])}, ocr_used: {result.get('ocr_used')}"
        )
        print(result["text"][:300])
        print()

    if skipped:
        print("--- skipped ---")
        for s in skipped:
            print(f"{s['path']}: {s['reason']}")


if __name__ == "__main__":
    main()