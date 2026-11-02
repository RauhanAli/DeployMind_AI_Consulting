"""Document ingestion: parse -> chunk -> embed -> store in pgvector, inside one transaction per document."""

import logging
import time
import uuid

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.ai.registry import get_embedder, record_usage
from app.models import AIApplication, Document, DocumentChunk
from app.models.knowledge import DEFAULT_RETRIEVAL
from app.rag.chunking import chunk_pages
from app.rag.parsing import parse
from app.rag.storage import get_storage

log = logging.getLogger("deploymind.ingest")


def ingest_document(db: Session, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"document {document_id} not found")
    doc.status = "processing"
    doc.error = None
    db.commit()
    try:
        cfg = dict(DEFAULT_RETRIEVAL)
        if doc.app_id:
            app = db.get(AIApplication, doc.app_id)
            cfg.update(app.retrieval_config or {})
        data = get_storage().get(doc.storage_key)
        pages = parse(doc.content_type, data)
        chunks = chunk_pages(pages, int(cfg["chunk_size"]), int(cfg["chunk_overlap"]))
        if not chunks:
            raise ValueError("No extractable text found in document")
        embedder = get_embedder()
        t0 = time.perf_counter()
        vectors, tokens = embedder.embed([f"{doc.title}\n{c.content}" for c in chunks])
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        db.add_all([
            DocumentChunk(organisation_id=doc.organisation_id, document_id=doc.id, app_id=doc.app_id,
                          ordinal=c.ordinal, content=c.content, token_count=c.token_count, page=c.page, embedding=v)
            for c, v in zip(chunks, vectors, strict=True)
        ])
        record_usage(db, org_id=doc.organisation_id, agent="ingestion", operation="embedding",
                     provider=embedder.name, model=embedder.model, input_tokens=tokens,
                     latency_ms=int((time.perf_counter() - t0) * 1000), app_id=doc.app_id, is_mock=embedder.is_mock)
        doc.chunk_count = len(chunks)
        doc.status = "ready"
        db.commit()
        log.info("document_ingested", extra={"document_id": str(doc.id), "chunks": len(chunks)})
    except Exception as exc:
        db.rollback()
        doc = db.get(Document, document_id)
        doc.status = "failed"
        doc.error = str(exc)[:1000]
        db.commit()
        log.exception("document_ingest_failed", extra={"document_id": str(document_id)})
    return doc
