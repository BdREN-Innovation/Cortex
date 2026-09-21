from engine.knowledge.chunking import chunk_document, ChunkConfig
from engine.knowledge.parsers import parse_document
from engine.contracts.documents import CleanDocument, content_hash, make_doc_id

path = "corpus/cuet/_files/de1bedf5__69e479fa7ce5b.pdf"
parsed = parse_document(path)
text = parsed["text"]

doc = CleanDocument(
    doc_id=make_doc_id(path),
    source_url=path,
    canonical_url=path,
    title="MME Syllabus",
    text=text,
    content_hash=content_hash(text),
    fetched_at="2026-09-11T00:00:00Z",
    doc_type="pdf",
)

config = ChunkConfig()
chunks = chunk_document(doc, config)

print(f"doc text length: {len(text)} chars, ~{len(text)//4} tokens")
print(f"produced {len(chunks)} chunks")
print()

for c in chunks:
    print(f"--- chunk {c.ordinal} (chunk_id={c.chunk_id}, ~{c.token_estimate} tokens, {len(c.text)} chars) ---")
    print(repr(c.text[:150]))
    print("...")
    print(repr(c.text[-100:]))
    print()