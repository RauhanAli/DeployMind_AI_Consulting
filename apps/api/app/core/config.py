"""Application settings loaded from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
_DEV_FERNET_KEY = "0pZQ4Hn0n3H0q2kQ1lZ8xGk3c9pYc6T2mJv4f1bXw0s="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), ".env"), extra="ignore", case_sensitive=False
    )

    app_env: str = "development"
    app_name: str = "DeployMind"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    log_format: str = "json"

    database_url: str = "postgresql+psycopg://deploymind:deploymind@localhost:55432/deploymind"
    test_database_url: str = "postgresql+psycopg://deploymind:deploymind@localhost:55432/deploymind_test"

    redis_url: str = "redis://localhost:56379/0"
    celery_broker_url: str = "redis://localhost:56379/1"
    celery_result_backend: str = "redis://localhost:56379/2"
    celery_task_always_eager: bool = False

    jwt_secret: str = "change-me-development-only-jwt-secret-please-rotate"  # noqa: S105  (dev default; refused in production)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    cookie_secure: bool = False

    secrets_encryption_key: str = _DEV_FERNET_KEY
    secrets_backend: str = "fernet"

    ai_provider: str = "mock"
    embedding_provider: str = "mock"
    embedding_dimensions: int = 384
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    ai_request_timeout_seconds: int = 60
    ai_max_retries: int = 2

    storage_backend: str = "local"
    storage_local_path: str = str(REPO_ROOT / "var" / "storage")
    s3_bucket: str = "deploymind-documents"
    s3_endpoint_url: str = ""
    s3_region: str = "eu-west-2"
    max_upload_mb: int = 20

    email_backend: str = "console"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "no-reply@deploymind.local"

    deploy_adapter: str = "local_docker"
    assistant_service_path: str = str(REPO_ROOT / "apps" / "assistant-service")
    local_deploy_port_range: str = "18100-18199"
    # Host shown to users for locally deployed containers, and the host the API/worker use to probe them
    # (inside docker-compose the worker must reach published ports via host.docker.internal).
    local_deploy_public_host: str = "localhost"
    local_deploy_probe_host: str = "localhost"
    platform_url_from_container: str = "http://host.docker.internal:8000"
    github_token: str = ""
    github_repository: str = ""
    github_deploy_workflow: str = "deploy.yml"
    aws_ecs_cluster: str = ""
    aws_ecs_service_prefix: str = "deploymind"
    aws_ecr_repository: str = ""

    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "deploymind-api"
    metrics_enabled: bool = True

    provider_org_slug: str = Field(default="deploymind", description="Slug of the internal provider organisation")

    @field_validator("storage_local_path", "assistant_service_path")
    @classmethod
    def _resolve_path(cls, v: str) -> str:
        p = Path(v)
        if not p.is_absolute():
            p = (REPO_ROOT / "apps" / "api" / p).resolve()
        return str(p)

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        """Refuse to boot production with development secrets or demo-only modes."""
        if self.app_env == "production":
            problems = []
            if self.jwt_secret.startswith("change-me") or len(self.jwt_secret) < 32:
                problems.append("JWT_SECRET must be a unique value of at least 32 characters")
            if self.secrets_encryption_key == _DEV_FERNET_KEY:
                problems.append("SECRETS_ENCRYPTION_KEY must not be the development key")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true behind HTTPS")
            if self.ai_provider == "mock":
                problems.append("AI_PROVIDER=mock is for demos only")
            if problems:
                raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def mock_ai(self) -> bool:
        return self.ai_provider == "mock"

    @property
    def deploy_port_range(self) -> tuple[int, int]:
        lo, hi = self.local_deploy_port_range.split("-")
        return int(lo), int(hi)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
