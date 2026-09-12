import json
from pathlib import Path
import pdfplumber
from engine.knowledge.pdf import _is_real_table

CORPUS_ROOT = Path("corpus/cuet")

pages = [json.loads(l) for l in open("corpus/cuet/pages.jsonl", encoding="utf-8")]
pdf_paths = [
    CORPUS_ROOT / p["content_path"]
    for p in pages
    if p.get("content_path", "").endswith(".pdf")
]

print(f"scanning {len(pdf_paths)} pdf docs...")

docs_with_real_tables = 0
total_real_tables = 0
per_doc_counts = []
errors = []

for i, path in enumerate(pdf_paths):
    if i % 25 == 0:
        print(f"  ...{i}/{len(pdf_paths)}")
    try:
        with pdfplumber.open(path) as pdf:
            doc_real = 0
            for page in pdf.pages:
                found = page.find_tables()
                doc_real += sum(1 for t in found if _is_real_table(t.extract()))
            if doc_real > 0:
                docs_with_real_tables += 1
                total_real_tables += doc_real
                per_doc_counts.append((str(path), doc_real))
    except Exception as e:
        errors.append((str(path), str(e)))

print()
print(f"total pdf docs scanned: {len(pdf_paths)}")
print(f"docs with >=1 real table: {docs_with_real_tables}")
print(f"total real tables found: {total_real_tables}")
print(f"errors during scan: {len(errors)}")
print()
print("top 10 docs by table count:")
for path, count in sorted(per_doc_counts, key=lambda x: -x[1])[:10]:
    print(f"  {count:3d}  {path}")
if errors:
    print()
    print("errors:")
    for path, err in errors[:10]:
        print(f"  {path}: {err}")