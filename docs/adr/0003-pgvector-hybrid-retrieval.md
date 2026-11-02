# ADR 0003: pgvector with hybrid retrieval

* Status: accepted
* Date: 2026-10-30

## Context
The knowledge assistant must respect tenant and document permissions, cite sources and refuse when evidence is
thin. Customers often already run PostgreSQL.

## Decision
* Store chunks in PostgreSQL with `vector(384)` (HNSW, cosine) and a generated `tsvector` (GIN).
* Retrieve with both and fuse them with **weighted reciprocal-rank fusion** (`vector_weight`, `keyword_weight`
  configurable per app and per evaluation run).
* Apply **tenant and ACL filters inside the SQL** (visibility + `document_permissions` join).
* Evidence gate before generation: top hybrid relevance ≥ `min_relevance` **and** the best chunk covers at least
  `min_term_coverage` of the question's content terms. Answers without valid citations are discarded in
  grounded mode.

## Consequences
* One datastore to operate, back up and secure. Joins make ACL enforcement simple and transactional.
* At very large corpora a dedicated vector store may be justified. The retrieval module is the seam to swap.
* Embedding dimension is fixed by the column type. Changing models means a migration and re-ingestion.
