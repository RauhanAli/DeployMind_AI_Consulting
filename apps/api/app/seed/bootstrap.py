"""Idempotent reference-data bootstrap: permissions, roles, question bank, model pricing, provider organisation."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import PERMISSIONS, ROLES
from app.models import ModelPricing, Organisation, Permission, Role
from app.services.assessments import sync_question_bank

# Illustrative list prices in USD per million tokens. Configurable at runtime via /costs/pricing;
# verify against the provider's current pricing page before relying on cost estimates.
DEFAULT_PRICING = [
    ("mock", "mock-deterministic-1", "0", "0", "Mock provider - no cost"),
    ("mock", "hashing-bow-v1", "0", "0", "Mock embeddings - no cost"),
    ("openai", "gpt-4o-mini", "0.15", "0.60", "Verify against current OpenAI pricing"),
    ("openai", "gpt-4o", "2.50", "10.00", "Verify against current OpenAI pricing"),
    ("openai", "text-embedding-3-small", "0.02", "0", "Verify against current OpenAI pricing"),
    ("anthropic", "claude-sonnet-5-5", "3.00", "15.00", "Verify against current Anthropic pricing"),
    ("anthropic", "claude-haiku-5-5", "1.00", "5.00", "Verify against current Anthropic pricing"),
    ("anthropic", "claude-opus-5-5", "5.00", "25.00", "Verify against current Anthropic pricing"),
]


def bootstrap(db: Session) -> Organisation:
    perms = {p.key: p for p in db.scalars(select(Permission)).all()}
    for key, desc in PERMISSIONS.items():
        if key not in perms:
            perms[key] = Permission(key=key, description=desc)
            db.add(perms[key])
        else:
            perms[key].description = desc
    db.flush()
    roles = {r.key: r for r in db.scalars(select(Role)).all()}
    for key, spec in ROLES.items():
        role = roles.get(key) or Role(key=key, name=spec["name"], scope=spec["scope"])
        role.name, role.scope, role.description = spec["name"], spec["scope"], spec["description"]
        role.permissions = [perms[p] for p in sorted(spec["permissions"])]
        db.add(role)
    sync_question_bank(db)
    existing = {(p.provider, p.model) for p in db.scalars(select(ModelPricing)).all()}
    for provider, model, inp, out, notes in DEFAULT_PRICING:
        if (provider, model) not in existing:
            db.add(ModelPricing(provider=provider, model=model, input_per_million=Decimal(inp),
                                output_per_million=Decimal(out), effective_from=date(2024, 1, 1), notes=notes))
    org = db.scalar(select(Organisation).where(Organisation.slug == settings.provider_org_slug))
    if org is None:
        org = Organisation(name="DeployMind", slug=settings.provider_org_slug, kind="provider",
                           industry="AI consulting & engineering", description="Internal provider organisation")
        db.add(org)
    db.flush()
    return org
