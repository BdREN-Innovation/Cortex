import argparse
import json
from pathlib import Path

from engine.contracts.documents import CleanDocument
from engine.knowledge.chunking import chunk_documents


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--site", required=True)

    args = parser.parse_args()

    run_dir = Path("scratch") / "corpus" / args.site

    documents_path = run_dir / "documents.jsonl"
    output_path = run_dir / "chunks.jsonl"

    docs = []

    with documents_path.open(encoding="utf-8") as f:
        for line in f:
            docs.append(
                CleanDocument.from_dict(json.loads(line))
            )

    print(f"loaded documents: {len(docs)}")

    chunks = chunk_documents(docs)

    print(f"created chunks: {len(chunks)}")

    with output_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(
                json.dumps(
                    chunk.__dict__,
                    ensure_ascii=False
                ) + "\n"
            )

    print(f"written -> {output_path}")


if __name__ == "__main__":
    main()