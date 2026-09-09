from engine.knowledge.parsers import parse_pdf, ENGINES

pdf_path = "fixtures/site/docs/plan-comparison.pdf"

for engine_name in ENGINES:
    result = parse_pdf(pdf_path, engine=engine_name)
    print(f"\n=== {engine_name} ===")
    print(f"empty: {result['empty']}, chars: {len(result['text'])}, tables: {len(result['tables'])}")
    print(result["text"][:500])