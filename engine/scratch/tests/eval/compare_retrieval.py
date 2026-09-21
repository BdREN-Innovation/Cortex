import json
from pathlib import Path
import numpy as np

from dotenv import load_dotenv
from engine.knowledge.embedding import build_embedder


load_dotenv()


CHUNKS = Path("scratch/tests/eval/sample_chunks.jsonl")
EMBED_DIR = Path("scratch/tests/embeddings")


def load_chunks():
    chunks = []

    with CHUNKS.open(encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))

    return chunks


def cosine_similarity(query, vectors):
    query = query / np.linalg.norm(query)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    return vectors @ query


def search(provider, model, vector_file, query, top_k=5):

    print("\n====================")
    print(provider, model)
    print("Query:", query)

    chunks = load_chunks()

    vectors = np.load(vector_file)

    embedder = build_embedder(
        provider=provider,
        model=model
    )

    q_vector = embedder.embed([query])[0]

    scores = cosine_similarity(
        q_vector,
        vectors
    )

    top = np.argsort(scores)[::-1][:top_k]

    for i in top:
        c = chunks[i]

        print("\nScore:", round(float(scores[i]),4))
        print("Title:", c.get("meta", {}).get("title", ""))

        sources = c.get("meta", {}).get("sources", [])
        if sources:
                print("Source:", sources[0].get("live_url"))

        print("Text:")
        print(c["text"][:300])


queries = [
    "GPU service tariff",
    "CUET admission requirement",
    "office order notice",
    "student admission",
    "research publication",
    "library service",
    "VPN service",
    "ভর্তি বিজ্ঞপ্তি",
    "অফিস আদেশ",
]


models = [
    (
        "cohere",
        "embed-multilingual-v3.0",
        EMBED_DIR / "cohere_embed_multilingual_v3.0.npy"
    ),
    (
        "openai",
        "text-embedding-3-small",
        EMBED_DIR / "openai_text_embedding_3_small.npy"
    ),
    (
        "openai",
        "text-embedding-3-large",
        EMBED_DIR / "openai_text_embedding_3_large.npy"
    ),
]


for q in queries:
    for m in models:
        search(*m, query=q)