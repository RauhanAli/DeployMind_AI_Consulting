from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.responses import Response

import app.ai.agents.assess  # noqa: F401  register agents
import app.ai.agents.delivery  # noqa: F401
import app.ai.agents.run  # noqa: F401
import app.ai.tools  # noqa: F401  register tools
from app.ai.agents.framework import AGENT_REGISTRY
from app.api.v1 import assess, auth, build, crm, deploy, integrations, knowledge, platform, projects, run
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware, configure_tracing
from app.db.session import SessionLocal, engine

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.seed.bootstrap import bootstrap

    with SessionLocal() as db:
        bootstrap(db)
        db.commit()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="DeployMind API",
        version="1.0.0",
        description="Assess → Build → Deploy → Run: enterprise AI consulting and production operations platform.",
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    for r in (auth, platform, assess, crm, build, projects, knowledge, integrations, deploy, run):
        app.include_router(r.router, prefix="/api/v1")

    @app.get("/health", tags=["ops"])
    def health():
        with engine.connect() as c:
            c.execute(text("select 1"))
        return {"status": "ok", "ai_provider": settings.ai_provider, "mock_ai": settings.mock_ai}

    @app.get("/api/v1/agents", tags=["ops"])
    def agents():
        return [{"name": s.name, "responsibility": s.responsibility, "tools": s.tools,
                 "input_schema": s.input_schema.__name__, "output_schema": s.output_schema.__name__,
                 "max_attempts": s.max_attempts} for s in AGENT_REGISTRY.values()] + [
            {"name": "knowledge_assistant_agent", "responsibility": "Grounded RAG answers with citations",
             "tools": ["hybrid_retrieval"], "input_schema": "question", "output_schema": "AssistantAnswer",
             "max_attempts": 1}]

    if settings.metrics_enabled:
        @app.get("/metrics", include_in_schema=False)
        def metrics():
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    configure_tracing(app)
    return app


app = create_app()
