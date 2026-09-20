import yaml
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from engine.contracts.evaluation import EvalCase
from engine.knowledge.retriever import load_retriever

raw = yaml.safe_load(Path("datasets/bdren/golden.v1.yaml").read_text(encoding="utf-8"))
cases = {c["case_id"]: EvalCase.from_dict(c) for c in raw["cases"]}
retriever = load_retriever("data/index/bdren/1c1e0d7984fd")

for cid in ["bdren_011", "bdren_014", "bdren_017", "bdren_040", "bdren_052"]:
    c = cases[cid]
    chunks = retriever.retrieve(c.question, top_k=50)
    for d in c.relevant_doc_ids:
        pos = next((i + 1 for i, x in enumerate(chunks) if x.doc_id == d), None)
        print(cid, d, "first chunk at position", pos or "not in top 50")
