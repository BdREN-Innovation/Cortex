import numpy as np

from engine.contracts.documents import CleanDocument, content_hash, make_doc_id
from engine.knowledge.chunking import ChunkConfig, chunk_document
from engine.knowledge.embedding import HashEmbedder, build_embedder
from engine.knowledge.rag import RagConfig, REFUSAL, answer
from engine.knowledge.retriever import VectorRetriever
from engine.knowledge.store import NumpyVectorStore


def make_doc(text, url="https://x.test/a", title="A"):
    return CleanDocument(
        doc_id=make_doc_id(url),
        source_url=url,
        canonical_url=url,
        title=title,
        text=text,
        content_hash=content_hash(text),
        fetched_at="2026-01-01T00:00:00+00:00",
        section_path=["Docs", title],
    )


def test_chunking_overlaps_and_carries_provenance():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(10))
    chunks = chunk_document(make_doc(text), ChunkConfig(target_tokens=100, overlap_tokens=20))
    assert len(chunks) > 1
    assert all(c.doc_id == chunks[0].doc_id for c in chunks)
    assert all(c.canonical_url == "https://x.test/a" for c in chunks)
    assert all(c.section_path == ["Docs", "A"] for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_short_document_is_one_chunk():
    chunks = chunk_document(make_doc("A single short paragraph."))
    assert len(chunks) == 1


def test_hash_embedder_is_deterministic_and_normalised():
    embedder = HashEmbedder(dimensions=64)
    a = embedder.embed(["refund policy for annual plans"])
    b = embedder.embed(["refund policy for annual plans"])
    assert np.allclose(a, b)
    assert np.isclose(np.linalg.norm(a[0]), 1.0)


def test_build_embedder_rejects_anthropic_for_embeddings():
    """Anthropic has no embeddings endpoint; the error must say so, not 500 later."""
    try:
        build_embedder("anthropic")
    except ValueError as exc:
        assert "embeddings" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")


def _retriever_over(docs):
    from engine.knowledge.chunking import chunk_documents

    chunks = chunk_documents(docs)
    embedder = HashEmbedder(dimensions=256)
    store = NumpyVectorStore(dimensions=256)
    store.add(chunks, embedder.embed([c.text for c in chunks]))
    return VectorRetriever(store, embedder, index_id="test")


def test_retriever_ranks_the_right_document_first():
    docs = [
        make_doc("Annual plans can be refunded within 30 days of purchase.", "https://x.test/refunds", "Refunds"),
        make_doc("The Free plan allows 3 projects and 1 GB of storage.", "https://x.test/limits", "Limits"),
        make_doc("We accept Visa, Mastercard and American Express.", "https://x.test/billing", "Billing"),
    ]
    hits = _retriever_over(docs).retrieve("how do refunds work on annual plans", top_k=3)
    assert hits[0].canonical_url == "https://x.test/refunds"


def test_store_round_trips_through_disk(tmp_path):
    docs = [make_doc("Storage overages cost 10 cents per gigabyte.", "https://x.test/limits")]
    retriever = _retriever_over(docs)
    retriever.store.save(tmp_path / "index")

    reloaded = NumpyVectorStore.load(tmp_path / "index")
    assert len(reloaded.chunks) == len(retriever.store.chunks)
    assert reloaded.chunks[0].canonical_url == "https://x.test/limits"


def test_rag_refuses_when_nothing_is_relevant():
    docs = [make_doc("Annual plans can be refunded within 30 days.", "https://x.test/refunds")]
    result = answer(
        "what is the airspeed velocity of an unladen swallow",
        _retriever_over(docs),
        RagConfig(provider="extractive", min_score=0.9),
    )
    assert result.refused is True
    assert result.text == REFUSAL
    assert result.citations == []


def test_rag_answers_with_citations():
    docs = [make_doc("Annual plans can be refunded within 30 days of purchase.", "https://x.test/refunds")]
    result = answer("refund annual plan", _retriever_over(docs), RagConfig(provider="extractive"))
    assert result.refused is False
    assert result.citations
    assert result.citations[0].canonical_url == "https://x.test/refunds"
