from engine.knowledge.extraction import extract

html_path = "fixtures/site/docs/plans.html"
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

result = extract(html, url="https://example.com/index.html")

print(f"title: {result.title}")
print(f"section_path: {result.section_path}")
print(f"tables found: {len(result.tables)}")
print("\n--- text ---")
print(result.text[:800])