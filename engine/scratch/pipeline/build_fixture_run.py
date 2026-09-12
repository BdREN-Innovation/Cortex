# scratch/build_fixture_run.py — DELETE once you're testing against real
# Team A runs instead of fixtures. Turns fixtures/site/docs into a fake
# run_dir (pages.jsonl + raw/ + docs/) so extract_documents() can run.

import json
import shutil
from pathlib import Path

FIXTURES = Path("fixtures/site/docs")
RUN_DIR = Path("data/sites/fixture/demo")


def build() -> None:
    raw_dir = RUN_DIR / "raw"
    docs_dir = RUN_DIR / "docs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for path in sorted(FIXTURES.iterdir()):
        if path.is_dir():
            continue

        suffix = path.suffix.lower()
        if suffix in (".html", ".htm"):
            dest = raw_dir / path.name
            shutil.copy(path, dest)
            content_path = f"raw/{path.name}"
            content_type = "html"
        elif suffix == ".pdf":
            dest = docs_dir / path.name
            shutil.copy(path, dest)
            content_path = f"docs/{path.name}"
            content_type = "pdf"
        elif suffix == ".docx":
            dest = docs_dir / path.name
            shutil.copy(path, dest)
            content_path = f"docs/{path.name}"
            content_type = "docx"
        else:
            continue  # robots.txt, etc — skip

        pages.append({
            "url": f"https://fixture.local/{path.stem}",
            "content_path": content_path,
            "content_type": content_type,
        })

    with (RUN_DIR / "pages.jsonl").open("w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p) + "\n")

    print(f"wrote {len(pages)} pages -> {RUN_DIR / 'pages.jsonl'}")


if __name__ == "__main__":
    build()