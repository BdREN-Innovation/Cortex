import json

from engine.contracts.documents import CleanDocument
from engine.knowledge.chunking import chunk_document, ChunkConfig
from engine.knowledge.embedding import build_embedder

documents = []

with open(
    "corpus/cuet/documents.jsonl",
    encoding="utf-8"
) as f:

    for i, line in enumerate(f):

        if i >= 5:
            break

        data = json.loads(line)

        doc = CleanDocument.from_dict(data)

        documents.append(doc)


print("Documents loaded:", len(documents))

all_chunks = []

config = ChunkConfig()

for doc in documents:

    chunks = chunk_document(
        doc,
        config
    )

    all_chunks.extend(chunks)

print("Chunks created:", len(all_chunks))

texts = [
    chunk.text
    for chunk in all_chunks
]

print("First chunk preview:")
print(texts[0][:200])

embedder = build_embedder(
    provider="gemini",
    model="gemini-embedding-001",
    dimensions=3072
)

vectors = embedder.embed(texts)

print("Embedding shape:", vectors.shape)
print("Vector dimension:", len(vectors[0]))