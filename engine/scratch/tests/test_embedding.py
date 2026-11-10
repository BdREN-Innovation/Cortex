import json
from pathlib import Path
import numpy as np

from dotenv import load_dotenv

from engine.knowledge.embedding import build_embedder


load_dotenv()


CHUNKS_PATH = Path("scratch/corpus/all/chunks.jsonl")
OUTPUT_DIR = Path("scratch/tests/embeddings")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_sample(n=100):
    texts = []

    with CHUNKS_PATH.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break

            chunk = json.loads(line)
            texts.append(chunk["text"])

    return texts


def test(provider, model):

    print("\nTesting:", provider, model)

    embedder = build_embedder(
        provider=provider,
        model=model
    )

    embedder.batch_size = 50

    vectors = embedder.embed(texts)

    print("Model:", embedder.name)
    print("Dimension:", embedder.dimensions)
    print("Shape:", vectors.shape)

    filename = (
        f"{provider}_{model.replace('-', '_')}.npy"
    )

    output = OUTPUT_DIR / filename

    np.save(output, vectors)

    print("Saved:", output)


texts = load_sample()

print("Loaded texts:", len(texts))


# Cohere
test(
    "cohere",
    "embed-multilingual-v3.0"
)


# OpenAI small
test(
    "openai",
    "text-embedding-3-small"
)


# OpenAI large
test(
    "openai",
    "text-embedding-3-large"
)