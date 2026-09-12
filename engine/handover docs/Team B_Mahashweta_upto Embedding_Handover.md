# Team B Knowledge Pipeline Notes

## Cortex Project --- CUET Knowledge Base

Pipeline:

    PDF / HTML Sources
            ↓
    Extraction + OCR
            ↓
    documents.jsonl
            ↓
    Cleaning + Duplicate Removal
            ↓
    Chunking
            ↓
    Embedding (Gemini)
            ↓
    Vector Storage (handled separately)

------------------------------------------------------------------------

# 1. Data Source Preparation

## Input

The crawler produced:

    pages.jsonl

Each entry contains:

-   URL
-   content path
-   content type
-   metadata

The extraction stage reads downloaded files offline.

Supported document types:

-   PDF
-   DOCX
-   HTML pages

------------------------------------------------------------------------

# 2. PDF Extraction and OCR

## Files

    src/engine/knowledge/pdf.py
    src/engine/knowledge/parsers.py

Pipeline:

    PDF file
       |
       +-- PyMuPDF text extraction
       |
       +-- pdfplumber table extraction
       |
       +-- OCR fallback (Tesseract)

OCR is used when:

-   PDF has no usable text layer
-   extracted text is too small or empty
-   scanned documents are detected

OCR usage is stored in metadata:

``` json
{
  "ocr_used": true
}
```

CUET extraction statistics:

    Total extracted documents: 416

    OCR documents: 207
    Non-OCR documents: 209

------------------------------------------------------------------------

# 3. Document Extraction

## File

    src/engine/knowledge/documents.py

Pipeline:

    pages.jsonl
          |
          v
    extract_documents()
          |
          v
    documents.jsonl

Each document follows the `CleanDocument` schema.

Important fields:

``` json
{
 "doc_id": "",
 "title": "",
 "text": "",
 "content_hash": "",
 "canonical_url": "",
 "section_path": [],
 "doc_type": "pdf",
 "meta": {}
}
```

------------------------------------------------------------------------

# 4. Duplicate Removal

Duplicate detection uses:

    content_hash(text)

The hash is generated from document text.

Purpose:

-   avoid duplicate embeddings
-   reduce API cost
-   prevent repeated retrieval results

Before cleanup:

    Documents: 416
    Unique contents: 393
    Extra duplicate copies: 23

After cleanup:

    documents.jsonl

    Documents: 393
    Unique contents: 393

------------------------------------------------------------------------

# 5. OCR Quality Checking

Command:

``` powershell
python scratch/scan_garbled_regions.py
```

Final check:

    Documents scanned: 416
    Judgeable paragraphs: 2082
    Garbled paragraphs: 16
    Documents affected: 9

Detected problems were mainly:

-   scanned forms
-   old PDFs
-   corrupted tables

------------------------------------------------------------------------

# 6. Chunking

## File

    src/engine/knowledge/chunking.py

Purpose:

Convert documents into retrieval units.

Pipeline:

    CleanDocument
           |
           v
    Chunk objects

Configuration:

``` python
ChunkConfig(
    target_tokens=350,
    overlap_tokens=60,
    min_tokens=40
)
```

Strategy:

-   split by paragraphs
-   preserve tables
-   split oversized sections
-   maintain overlap

------------------------------------------------------------------------

# 7. Chunk Validation

Command:

``` powershell
python scratch/check_corpus_chunks.py
```

Result:

    Checked documents: 416
    Total chunks: 3392

    Clean: 400
    Flagged: 16
    Crashed: 0

------------------------------------------------------------------------

# 8. Embedding Model

## File

    src/engine/knowledge/embedding.py

Selected model:

    Provider:
    Google Gemini

    Model:
    gemini-embedding-001

    Dimension:
    3072

Reason:

-   multilingual support
-   suitable for Bengali + English content
-   already supported by project dependencies

------------------------------------------------------------------------

# 9. Environment Configuration

Required `.env` variable:

``` env
GEMINI_API_KEY=<API_KEY>
```

The embedding module loads the Gemini client using this key.

------------------------------------------------------------------------

# 10. Embedding Output

Input:

    chunk.text

Output:

    numpy.ndarray

Shape:

    (number_of_chunks, 3072)

Flow:

    Chunk text
         |
         v
    Gemini Embedding API
         |
         v
    3072-dimensional vector

------------------------------------------------------------------------

# 11. Embedding Validation Tests

## Single text test

Result:

    Shape: (1,3072)

## Multiple text test

Result:

    Shape: (3,3072)

    Vector length:
    3072

## Real CUET pipeline test

Command:

``` powershell
python scratch/test_cuet_embedding.py
```

Result:

    Documents loaded: 5

    Chunks created: 100

    Embedding shape: (100,3072)

    Vector dimension: 3072

This confirms:

    documents.jsonl
            ↓
    chunk_document()
            ↓
    Chunk objects
            ↓
    Gemini embeddings

works correctly.

------------------------------------------------------------------------

# 12. Handoff Information

The indexing team receives:

    Chunk objects
    +
    Embedding vectors

Embedding configuration:

    Provider:
    Gemini

    Model:
    gemini-embedding-001

    Dimension:
    3072

    Input:
    chunk.text

    Output:
    numpy.ndarray

    Normalization:
    Applied before returning vectors

------------------------------------------------------------------------

# 13. Remaining Work

Handled by indexing/retrieval teammate:

    store.py
    indexer.py
    Qdrant
    vector persistence
    retriever.py
    RAG answering

------------------------------------------------------------------------

# Current Status

  Component                Status
  ------------------------ ----------
  PDF extraction           Complete
  OCR pipeline             Complete
  Document generation      Complete
  Duplicate removal        Complete
  Chunking                 Complete
  Chunk validation         Complete
  Gemini embedding         Complete
  Vector generation test   Complete
  Index storage            Pending
