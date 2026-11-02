"""Hybrid retrieval (pgvector cosine + Postgres full-text) fused with weighted reciprocal-rank fusion.

Access control is applied *inside* the SQL so unauthorised chunks are never loaded into the process:
- tenant: chunk.organisation_id == application's organisation
- document visibility: 'organisation' visible to all members; 'internal' only to provider staff;
  'restricted' only to explicitly listed users (and provider staff).
"""

import re
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.ai.registry import get_embedder
from app.models import AIApplication, Document, DocumentChunk, document_permissions
from app.models.knowledge import DEFAULT_RETRIEVAL
from app.rag.text import coverage, terms

RRF_K = 60


@dataclass
class Retrieved:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    title: str
    ordinal: int
    page: int | None
    content: str
    vector_similarity: float
    keyword_rank: float
    fused_score: float
    relevance: float


@dataclass
class RetrievalResult:
    chunks: list[Retrieved]
    retrieval_ms: int
    config: dict
    embedding_tokens: int

    @property
    def top_relevance(self) -> float:
        return max((c.relevance for c in self.chunks), default=0.0)


def _acl(user_id: uuid.UUID | None, is_internal: bool):
    if is_internal:
        return Document.visibility.in_(["organisation", "internal", "restricted"])
    restricted_ok = and_(
        Document.visibility == "restricted",
        exists().where(document_permissions.c.document_id == Document.id, document_permissions.c.user_id == user_id),
    ) if user_id else False
    return or_(Document.visibility == "organisation", restricted_ok)


def _tsquery(question: str) -> str | None:
    toks = [re.sub(r"[^a-z0-9]", "", t) for t in terms(question)]
    toks = [t for t in dict.fromkeys(toks) if len(t) > 1]
    return " | ".join(toks) if toks else None


def retrieve(db: Session, app: AIApplication, question: str, *, user_id: uuid.UUID | None, is_internal: bool,
             config_override: dict | None = None) -> RetrievalResult:
    cfg = {**DEFAULT_RETRIEVAL, **(app.retrieval_config or {}), **(config_override or {})}
    top_k, pool = int(cfg["top_k"]), int(cfg["top_k"]) * 4
    t0 = time.perf_counter()
    vectors, emb_tokens = get_embedder().embed([question])
    qv = vectors[0]

    base = (
        select(DocumentChunk.id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.organisation_id == app.organisation_id, DocumentChunk.app_id == app.id,
               Document.organisation_id == app.organisation_id, Document.status == "ready",
               _acl(user_id, is_internal))
    )
    distance = DocumentChunk.embedding.cosine_distance(qv)
    vec_rows = db.execute(base.add_columns((1 - distance).label("sim")).order_by(distance).limit(pool)).all()
    vec_rank = {r.id: (i + 1, float(r.sim)) for i, r in enumerate(vec_rows)}

    kw_rank: dict[uuid.UUID, tuple[int, float]] = {}
    tsq = _tsquery(question)
    if tsq:
        q = func.to_tsquery("english", tsq)
        rank = func.ts_rank_cd(DocumentChunk.tsv, q)
        kw_rows = db.execute(base.add_columns(rank.label("rank")).where(DocumentChunk.tsv.op("@@")(q))
                             .order_by(rank.desc()).limit(pool)).all()
        kw_rank = {r.id: (i + 1, float(r.rank)) for i, r in enumerate(kw_rows)}

    vw, kw = float(cfg["vector_weight"]), float(cfg["keyword_weight"])
    fused: dict[uuid.UUID, float] = {}
    for cid in set(vec_rank) | set(kw_rank):
        s = 0.0
        if cid in vec_rank:
            s += vw / (RRF_K + vec_rank[cid][0])
        if cid in kw_rank:
            s += kw / (RRF_K + kw_rank[cid][0])
        fused[cid] = s
    best = sorted(fused, key=lambda c: fused[c], reverse=True)[:top_k]
    if not best:
        return RetrievalResult([], int((time.perf_counter() - t0) * 1000), cfg, emb_tokens)

    rows = db.execute(
        select(DocumentChunk, Document.filename, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id).where(DocumentChunk.id.in_(best))
    ).all()
    by_id = {c.id: (c, fn, title) for c, fn, title in rows}
    out = []
    for cid in best:
        c, fn, title = by_id[cid]
        sim = vec_rank.get(cid, (0, 0.0))[1]
        # Relevance: blend of semantic similarity and lexical coverage of the question's content terms.
        rel = round(0.5 * max(sim, 0.0) + 0.5 * coverage(question, f"{title} {c.content}"), 4)
        out.append(Retrieved(chunk_id=cid, document_id=c.document_id, filename=fn, title=title, ordinal=c.ordinal,
                             page=c.page, content=c.content, vector_similarity=round(sim, 4),
                             keyword_rank=round(kw_rank.get(cid, (0, 0.0))[1], 4), fused_score=round(fused[cid], 5),
                             relevance=rel))
    out.sort(key=lambda r: r.relevance, reverse=True)
    return RetrievalResult(out, int((time.perf_counter() - t0) * 1000), cfg, emb_tokens)
