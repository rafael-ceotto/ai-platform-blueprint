# ADR-0005: Document Loaders — `pypdf` + BeautifulSoup over `langchain-community`

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-08 |
| **Deciders** | AI Platform Blueprint team |
| **Related** | [ADR-0004: LangChain for Answer Generation](0004-langchain-for-answer-generation.md) |

## Context

The reference document requires ingestion from PDF, Markdown, TXT, and
HTML — `POST /documents` only accepted raw text via JSON. ADR-0004
deliberately left the loader library choice open ("evaluate
`langchain-community`'s loaders at that point"); this is that point.

## Decision Drivers

- **Dependency weight proportional to what's used** — the same reasoning
  as ADR-0001 and ADR-0004's choice to add only `langchain-core` +
  `langchain-ollama`, not the full `langchain` package.
- **`.txt`/`.md` need no library at all** — markdown is already plain
  text; decoding is the entire "extraction" step.

## Options Considered

### Option A — Dedicated libraries (`pypdf`, `beautifulsoup4`)

**Pros**
- Both are lightweight, single-purpose, widely-used libraries with no
  heavy transitive dependencies.
- Only two new dependencies total; `.txt`/`.md` need none.

**Cons**
- One small loader module per format to own and test, instead of an
  off-the-shelf `langchain_community.document_loaders` class.

### Option B — `langchain-community` document loaders

**Pros**
- `PyPDFLoader`/`UnstructuredHTMLLoader` etc. are one import away, and
  match the reference doc's tech stack literally.
- Consistent loader interface (`.load()` returning LangChain `Document`s).

**Cons**
- The HTML/Markdown loaders that produce good results
  (`UnstructuredHTMLLoader`, `UnstructuredMarkdownLoader`) depend on the
  `unstructured` package, which pulls in a large, slow-to-install
  dependency tree (NLP/ML libraries, format-specific parsers) for
  functionality this project doesn't otherwise need.
- Adds `langchain-community` as a new dependency surface beyond the
  `langchain-core`/`langchain-ollama` scope ADR-0004 intentionally kept
  narrow.

## Decision

**Adopt `pypdf` for PDF and `beautifulsoup4` for HTML.** `.txt`/`.md`/
`.markdown` are read as plain UTF-8 text with no library. All four are
dispatched by file extension in `ingestion/loaders/dispatch.py`, and the
extracted text feeds the **existing, unchanged** `IngestionService`
(chunk → embed → store) via the new `POST /documents/upload` endpoint —
loaders are purely a text-extraction step upstream of a pipeline that
doesn't know or care a file was involved.

Uploads are capped at `MAX_UPLOAD_SIZE_BYTES` (default 10 MB, checked
before parsing) since reading an arbitrarily large file fully into memory
is an uncontrolled resource-exhaustion path with no other guard today.

## Revisit Triggers

- More formats are needed (DOCX, PPTX, CSV) at a rate where hand-rolling
  each loader stops being cheap → reconsider `langchain-community` or
  `unstructured` directly at that point, once the dependency cost is
  justified by breadth, not just one more format.
- PDF or HTML extraction quality becomes a real problem (e.g., tables,
  multi-column layouts, scanned/OCR'd PDFs) → `pypdf`'s plain-text
  extraction won't handle that; evaluate `unstructured` or a
  layout-aware extractor specifically for that gap.

## Consequences

- `ingestion/loaders/` (doc-anticipated, previously empty) now holds
  `pdf_loader.py`, `html_loader.py`, `dispatch.py`.
- `POST /documents/upload` is additive — `POST /documents` (raw text)
  is unchanged, and both converge on the same `IngestionService`.
- A future switch to `langchain-community` loaders would replace
  `ingestion/loaders/dispatch.py`'s implementation only; callers
  (`backend/api/v1/endpoints/documents.py`) wouldn't change.
