"""Merge the two scrape zips into corpus/cuet/_files and emit pages.jsonl."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ENGINE_ROOT / "corpus" / "cuet"
FILES_DIR = RUN_DIR / "_files"
INDEX_PATH = FILES_DIR / "index.json"

# Adjust these two if your extracted zip folders live somewhere else.
ZIP_SOURCES = [
    Path(r"C:\Users\USER\Downloads\scratch\zip1\01_scraped_documents"),   # older, 9/8
    Path(r"C:\Users\USER\Downloads\scratch\zip2\02_scrapped_documents"),  # newer, 9/9 — wins on collision
]

CONTENT_TYPE_BY_EXT = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def merge_files() -> int:
    """Copy PDFs/docs from both zip folders into _files/, later source wins."""
    copied = 0
    for src_dir in ZIP_SOURCES:
        if not src_dir.exists():
            print(f"skip (not found): {src_dir}")
            continue
        for f in src_dir.iterdir():
            if f.suffix.lower() not in CONTENT_TYPE_BY_EXT:
                continue
            shutil.copy2(f, FILES_DIR / f.name)
            copied += 1
    return copied


def build_pages():
    entries = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    pages = []
    skipped_not_downloaded = 0
    skipped_missing_file = 0

    for entry in entries:
        if not entry.get("downloaded"):
            skipped_not_downloaded += 1
            continue

        local = entry.get("local", "")
        filename = Path(local).name
        file_path = FILES_DIR / filename

        if not file_path.exists():
            skipped_missing_file += 1
            continue

        ext = file_path.suffix.lower()
        content_type = entry.get("content_type") or CONTENT_TYPE_BY_EXT.get(ext, "application/octet-stream")
        fetched_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()

        sources = entry.get("sources", [])
        parent_url = sources[0]["live_url"] if sources else (entry.get("linked_from") or [""])[0]

        page = {
            "page_id": file_path.stem,
            "url": entry["url"],
            "canonical_url": entry["url"],
            "status": 200,
            "content_type": content_type,
            "content_path": f"_files/{filename}",
            "fetched_at": fetched_at,
            "depth": 0,
            "links": [],
            "document_links": [],
            "parent_url": parent_url,
            "meta": {
                "document_type": entry.get("document_type", ""),
                "title": entry.get("title", ""),
                "category": entry.get("category", ""),
                "department": entry.get("department", ""),
                "sources": sources,
            },
        }
        pages.append(page)

    return pages, skipped_not_downloaded, skipped_missing_file


def main():
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    copied = merge_files()
    print(f"copied {copied} files from zips into {FILES_DIR}")

    pages, skipped_not_downloaded, skipped_missing_file = build_pages()

    out_path = RUN_DIR / "pages.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"wrote {len(pages)} pages -> {out_path}")
    print(f"skipped (downloaded=false in index): {skipped_not_downloaded}")
    print(f"skipped (listed downloaded=true but file missing locally): {skipped_missing_file}")


if __name__ == "__main__":
    main()