"""Provider selection and model-usage accounting."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers.base import EmbeddingProvider, LLMProvider, LLMResult, ProviderError
from app.ai.providers.mock import HashingEmbeddingProvider, MockLLMProvider
from app.core.config import settings
from app.core.tracing import current_trace_id
from app.domain.workflow import estimate_cost
from app.models import ModelPricing, ModelUsage

PROVIDERS = ("mock", "openai", "anthropic")


def get_llm(provider: str | None = None) -> LLMProvider:
    name = provider or settings.ai_provider
    if name == "mock":
        return MockLLMProvider()
    if name == "openai":
        from app.ai.providers.vendors import OpenAIProvider
        return OpenAIProvider()
    if name == "anthropic":
        from app.ai.providers.vendors import AnthropicProvider
        return AnthropicProvider()
    raise ProviderError(f"Unknown AI provider '{name}'")


def get_embedder() -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        from app.ai.providers.vendors import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider()
    return HashingEmbeddingProvider()


def provider_status() -> list[dict]:
    return [
        {"provider": "mock", "configured": True, "description": "Deterministic local provider (demo mode)"},
        {"provider": "openai", "configured": bool(settings.openai_api_key), "default_model": settings.openai_model},
        {"provider": "anthropic", "configured": bool(settings.anthropic_api_key),
         "default_model": settings.anthropic_model},
    ]


def pricing_for(db: Session, provider: str, model: str, on: date | None = None) -> tuple[Decimal, Decimal] | None:
    on = on or date.today()
    row = db.scalar(
        select(ModelPricing).where(ModelPricing.provider == provider, ModelPricing.model == model,
                                   ModelPricing.effective_from <= on)
        .order_by(ModelPricing.effective_from.desc()).limit(1)
    )
    return (row.input_per_million, row.output_per_million) if row else None


def record_usage(db: Session, *, org_id: uuid.UUID, agent: str, result: LLMResult | None = None,
                 provider: str | None = None, model: str | None = None, input_tokens: int = 0,
                 output_tokens: int = 0, latency_ms: int = 0, operation: str = "chat", success: bool = True,
                 project_id: uuid.UUID | None = None, app_id: uuid.UUID | None = None,
                 is_mock: bool | None = None) -> ModelUsage:
    if result is not None:
        provider, model = result.provider, result.model
        input_tokens, output_tokens, latency_ms = result.input_tokens, result.output_tokens, result.latency_ms
        is_mock = result.is_mock
    cost = estimate_cost(input_tokens, output_tokens, pricing_for(db, provider or "mock", model or "unknown"))
    usage = ModelUsage(
        organisation_id=org_id, project_id=project_id, app_id=app_id, agent=agent, operation=operation,
        provider=provider or "unknown", model=model or "unknown", input_tokens=input_tokens,
        output_tokens=output_tokens, cost_usd=cost, latency_ms=latency_ms, success=success,
        is_mock=bool(is_mock), trace_id=current_trace_id(), created_at=datetime.now(UTC),
    )
    db.add(usage)
    return usage
