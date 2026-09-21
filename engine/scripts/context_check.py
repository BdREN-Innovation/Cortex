import yaml
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from engine.contracts.evaluation import EvalCase
from engine.knowledge.rag import build_context
from engine.knowledge.retriever import load_retriever

raw = yaml.safe_load(Path("datasets/bdren/golden.v1.yaml").read_text(encoding="utf-8"))
cases = [EvalCase.from_dict(c) for c in raw["cases"]]
retriever = load_retriever("data/index/bdren/1c1e0d7984fd")

def has(chunks, expected):
    text = " ".join(x.text for x in chunks).lower()
    return all(s.lower() in text for s in expected)

print("case   in_top5  in_context  chunks_dropped")
for c in cases:
    if not c.answerable or not c.expected_answer_contains:
        continue
    chunks = retriever.retrieve(c.question, top_k=5)
    _, used = build_context(chunks, max_chars=8000)
    a = has(chunks, c.expected_answer_contains)
    b = has(used, c.expected_answer_contains)
    if not (a and b):
        print(c.case_id, a, b, len(chunks) - len(used))
