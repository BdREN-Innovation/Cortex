import argparse
from pathlib import Path
import json

from engine.knowledge.documents import extract_documents, ExtractConfig


def add_sources(output, site):
    docs = []

    with output.open(encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)

            meta = doc.get("meta", {})

            if "sources" not in meta:
                meta["sources"] = [
                    {
                        "live_url": doc.get("canonical_url"),
                        "origin": f"{site} crawl"
                    }
                ]

            doc["meta"] = meta
            docs.append(doc)

    with output.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--site", required=True)
    parser.add_argument("--run", required=True)

    args = parser.parse_args()

    run_dir = Path(args.run)

    output_dir = Path("scratch") / "corpus" / args.site
    output_dir.mkdir(parents=True, exist_ok=True)

    output = output_dir / "documents.jsonl"

    extract_documents(
        run_dir=run_dir,
        config=ExtractConfig(),
        out_path=output,
    )

    add_sources(output, args.site)

    print(f"done -> {output}")


if __name__ == "__main__":
    main()