# Cortex Knowledge Corpus Pipeline - Detailed Handoff Documentation

## 1. Purpose and Scope

This document explains the complete workflow used to prepare the Cortex knowledge corpus.

The completed responsibility of this stage includes:

- Collecting scraped documents
- Creating page metadata
- Extracting clean documents
- Handling PDF/DOC/DOCX files
- Preserving citation metadata
- Generating chunks
- Testing embedding models

The next stage starts from embeddings and handles:

- Vector storage
- Indexing
- Retrieval
- RAG pipeline

---

# 2. Overall Pipeline Architecture

```
Raw scraped documents
        |
        v
_files/
        |
        v
pages.jsonl
        |
        v
documents.jsonl
        |
        v
chunks.jsonl
        |
        v
Embedding generation
        |
        v
Vector database / indexing (Next stage)
```

---

# 3. CUET Corpus Creation

## 3.1 Source Data

CUET was handled separately because its citation metadata structure was different from the other sources.

The scraped document folders used:

```
Attachment/
├── 01_scraped_documents
└── 02_scrapped_documents
```

These folders contained:

- PDF files
- DOC files
- DOCX files
- index.json metadata

---

# 3.2 CUET pages.jsonl Generation

Script:

```
scratch/pipeline/build_cuet_pages.py
```

Purpose:

- Merge scraped document sources
- Copy documents into the corpus file directory
- Merge metadata from index files
- Create page-level metadata

Run:

```powershell
uv run python scratch\pipeline\build_cuet_pages.py
```

Output:

```
scratch/corpus/cuet/
├── _files/
└── pages.jsonl
```

Each page entry stores:

- document URL
- canonical URL
- content path
- content type
- title
- category
- author
- source information

Example metadata:

```json
{
  "url": "...",
  "canonical_url": "...",
  "content_path": "_files/file.pdf",
  "meta": {
    "sources": [
      {
        "live_url": "...",
        "title": "...",
        "author": "...",
        "category": "..."
      }
    ]
  }
}
```

---

# 3.3 CUET Document Extraction

Document extraction is handled by:

```
src/engine/knowledge/documents.py
```

Flow:

```
pages.jsonl
      |
      v
extract_documents()
      |
      v
documents.jsonl
```

Responsibilities:

- Read page metadata
- Detect file type
- Extract text
- Create CleanDocument objects
- Preserve metadata

Output:

```
scratch/corpus/cuet/documents.jsonl
```

---

# 3.4 CUET DOC File Issue and Fix

Problem:

Some CUET documents were old Microsoft Word `.doc` files.

Direct extraction resulted in corrupted text:

```
� � �
```

Reason:

`.doc` uses an old binary OLE format.

Solution:

```
.doc
 |
 v
LibreOffice headless conversion
 |
 v
.docx
 |
 v
DOCX parser
 |
 v
Clean text
```

LibreOffice verification:

```powershell
& "C:\Program Files\LibreOffice\program\soffice.exe" --version
```

---

# 3.5 CUET Citation Verification Before Chunking

Before chunking, citation metadata was checked inside:

```
documents.jsonl
```

Verified fields:

- live_url
- title
- author
- category
- source information

Example:

```json
"meta": {
  "sources": [
    {
      "live_url": "...",
      "title": "...",
      "author": "...",
      "category": "..."
    }
  ]
}
```

---

# 3.6 CUET Chunk Generation

Script:

```
scratch/pipeline/build_cuet_chunks.py
```

Run:

```powershell
uv run python scratch\pipeline\build_cuet_chunks.py
```

Flow:

```
documents.jsonl
        |
        v
CleanDocument objects
        |
        v
chunk_documents()
        |
        v
chunks.jsonl
```

Output:

```
scratch/corpus/cuet/chunks.jsonl
```

---

# 3.7 CUET Citation Verification After Chunking

After chunk generation, citation metadata was checked again.

Verified:

```
chunks.jsonl
```

contains:

```
chunk
 |
 ├── canonical_url
 └── meta.sources
```

This confirmed citation information survived the chunking process.

---

# 4. UIU Corpus Creation

## 4.1 Source Data

Location:

```
scratch/corpus/uiu/
```

UIU followed the standard site pipeline.

---

## 4.2 UIU pages.jsonl Generation

The scraped UIU data was processed into:

```
pages.jsonl
```

containing:

- page URL
- canonical URL
- content path
- metadata
- source information

---

## 4.3 UIU documents.jsonl Generation

The standard document extraction pipeline was used.

Script:

```
scratch/pipeline/build_site_documents.py
```

Flow:

```
pages.jsonl
        |
        v
documents.py extraction
        |
        v
documents.jsonl
```

---

## 4.4 UIU Citation Verification

Before chunking:

Checked:

```
documents.jsonl
```

Confirmed:

- source URL exists
- title exists
- metadata is preserved

---

## 4.5 UIU Chunk Generation

Script:

```
scratch/pipeline/build_site_chunks.py
```

Input:

```
documents.jsonl
```

Output:

```
chunks.jsonl
```

Citation metadata was verified after chunking.

---

# 5. Green University Corpus Creation

## 5.1 Source Data

Location:

```
scratch/corpus/green/
```

---

## 5.2 Green pages.jsonl

Scraped documents were converted into:

```
pages.jsonl
```

containing document metadata and source information.

---

## 5.3 Green documents.jsonl

Generated using:

```
build_site_documents.py
```

Flow:

```
pages.jsonl
        |
        v
documents.jsonl
```

---

## 5.4 Green Citation Verification

Checked before chunking:

```
documents.jsonl
```

Verified:

- URL
- title
- source metadata

---

## 5.5 Green Chunk Generation

Generated:

```
chunks.jsonl
```

using:

```
build_site_chunks.py
```

Citation metadata was verified after chunking.

---

# 6. BDREN Corpus Creation

## 6.1 Source Data

Location:

```
scratch/corpus/bdren/
```

---

## 6.2 BDREN pages.jsonl

Scraped BDREN data was converted into:

```
pages.jsonl
```

---

## 6.3 BDREN documents.jsonl

Generated through:

```
build_site_documents.py
```

Flow:

```
pages.jsonl
        |
        v
documents.jsonl
```

---

## 6.4 BDREN Citation Verification

Checked:

```
documents.jsonl
```

Confirmed citation information remained available.

---

## 6.5 BDREN Chunk Generation

Generated:

```
chunks.jsonl
```

using:

```
build_site_chunks.py
```

Citation metadata was checked after chunking.

---

# 7. Combining All Chunk Data

After generating individual chunks:

```
bdren/chunks.jsonl
uiu/chunks.jsonl
green/chunks.jsonl
cuet/chunks.jsonl
```

they were combined into:

```
scratch/corpus/all/chunks.jsonl
```

Final corpus size:

```
5039 chunks
```

Breakdown:

| Corpus | Chunks |
|---|---:|
| UIU | 2199 |
| CUET | 1171 |
| Green | 1102 |
| BDREN | 567 |

---

# 8. Chunking Summary

The chunking stage converted extracted documents into smaller retrieval-ready units.

Each chunk maintains:

- chunk_id
- document_id
- text
- canonical URL
- citation metadata

Example:

```json
{
 "chunk_id": "...",
 "doc_id": "...",
 "text": "...",
 "canonical_url": "...",
 "meta": {
   "sources": []
 }
}
```

The main goal was:

- create manageable text units
- preserve document relationships
- maintain citation information

---

# 9. Embedding Generation and Testing

Embedding was performed after chunk generation.

Test script:

```
scratch/tests/test_embedding.py
```

Models tested:

## Cohere

```
embed-multilingual-v3.0
```

Dimension:

```
1024
```

## OpenAI Small

```
text-embedding-3-small
```

Dimension:

```
1536
```

## OpenAI Large

```
text-embedding-3-large
```

Dimension:

```
3072
```

Run:

```powershell
uv run python scratch\tests\test_embedding.py
```

Generated vector files:

```
scratch/tests/embeddings/
```

---

# 10. Embedding Evaluation

Evaluation was performed using:

```
scratch/tests/eval/
```

Process:

1. Select sample chunks
2. Generate embeddings
3. Embed queries
4. Compare cosine similarity

No vector database or indexing was created.

---

# 11. Final Handoff Boundary

Completed:

✅ Corpus collection  
✅ pages.jsonl generation  
✅ documents.jsonl generation  
✅ PDF/DOC/DOCX extraction  
✅ DOC conversion handling  
✅ Citation preservation  
✅ Chunk generation  
✅ Embedding generation/testing  

Next teammate responsibility:

⬜ Vector storage  
⬜ Indexing  
⬜ Retrieval system  
⬜ RAG pipeline  

---

# Important Files

```
src/engine/knowledge/
    parsers.py
    documents.py
    chunking.py
    embedding.py

scratch/pipeline/
    build_cuet_pages.py
    build_cuet_chunks.py
    build_site_documents.py
    build_site_chunks.py

scratch/tests/
    test_embedding.py
```

END OF HANDOFF

Corpus ZIP Drive Link:[ https://drive.google.com/file/d/1-awSAFgHXlAT1aNEvQJnngQHFFHCqgIw/view?usp=sharing](url)
