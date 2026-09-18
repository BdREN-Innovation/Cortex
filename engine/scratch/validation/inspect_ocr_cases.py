import json

ids = [
"28413e509e61c47f",
"0fcaf2ea3fcff5e7",
"e2f57246434c1d64",
"f2dc728e5a5ca5f1",
"2065af98e153365d",
"0bb35beffbdf079b",
"3a2b0705c47ebc99",
"f3c9febdc0affa3c",
"9cb455d8c8c15672",
]

with open("corpus/cuet/documents.jsonl", encoding="utf8") as f:
    for line in f:
        d=json.loads(line)

        if d["doc_id"] in ids:
            print("="*80)
            print(d["doc_id"])
            print(d["title"])
            print("="*80)
            print(d["text"][:1500])
            print("\n\n")