"""Build chunks.jsonl from documents.jsonl."""

import json
from pathlib import Path

from engine.contracts.documents import CleanDocument
from engine.knowledge.chunking import chunk_documents


ENGINE_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ENGINE_ROOT / "corpus" / "cuet"

DOCUMENTS_PATH = RUN_DIR / "documents.jsonl"
OUTPUT_PATH = RUN_DIR / "chunks.jsonl"


def load_documents():
    docs = []

    with DOCUMENTS_PATH.open(encoding="utf-8") as f:
        for line in f:
            docs.append(
                CleanDocument.from_dict(json.loads(line))
            )

    return docs


def main():
    docs = load_documents()

    print(f"loaded documents: {len(docs)}")

    chunks = chunk_documents(docs)

    print(f"created chunks: {len(chunks)}")

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(
                json.dumps(
                    chunk.__dict__,
                    ensure_ascii=False
                ) + "\n"
            )

    print(f"written -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()