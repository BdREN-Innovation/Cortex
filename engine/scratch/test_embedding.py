from engine.knowledge.embedding import build_embedder

embedder = build_embedder(
    "gemini",
    "gemini-embedding-001",
    3072
)

texts = [
    "CUET admission notice",
    "Department of Computer Science and Engineering syllabus",
    "Academic calendar 2026"
]

vectors = embedder.embed(texts)

print("Shape:", vectors.shape)
print("First vector length:", len(vectors[0]))