import logging
import time
import uuid
from collections import defaultdict

import redis
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.logging import request_id_var

log = logging.getLogger("deploymind.http")

HTTP_REQUESTS = Counter("deploymind_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "deploymind_http_request_duration_seconds", "HTTP request latency", ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
DOCS_CSP = "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; img-src 'self' data: fastapi.tiangolo.com"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            elapsed = time.perf_counter() - start
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            HTTP_REQUESTS.labels(request.method, route_path, str(status)).inc()
            HTTP_LATENCY.labels(request.method, route_path).observe(elapsed)
            if not request.url.path.startswith(("/health", "/metrics")):
                log.info("request", extra={"method": request.method, "path": request.url.path,
                                           "status": status, "duration_ms": round(elapsed * 1000, 1)})
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path in ("/docs", "/redoc"):
            response.headers["Content-Security-Policy"] = DOCS_CSP
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


class RateLimiter:
    """Fixed-window limiter backed by Redis, with an in-process fallback if Redis is unreachable."""

    def __init__(self) -> None:
        self._redis = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
        self._local: dict[str, int] = defaultdict(int)
        self._redis_ok = True

    def hit(self, key: str, limit: int, window: int = 60) -> bool:
        bucket = f"rl:{key}:{int(time.time() // window)}"
        if self._redis_ok:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(bucket)
                pipe.expire(bucket, window + 1)
                count = pipe.execute()[0]
                return int(count) <= limit
            except redis.RedisError:
                self._redis_ok = False
                log.warning("rate_limiter_redis_unavailable_using_local_fallback")
        self._local[bucket] += 1
        if len(self._local) > 10000:
            self._local.clear()
        return self._local[bucket] <= limit


limiter = RateLimiter()

AUTH_PATHS = ("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path.startswith("/api/"):
            ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
            if path in AUTH_PATHS:
                allowed = limiter.hit(f"auth:{ip}", settings.auth_rate_limit_per_minute)
            else:
                allowed = limiter.hit(f"api:{ip}", settings.rate_limit_per_minute)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": "60"},
                    content={"error": {"code": "rate_limited", "message": "Too many requests, retry later",
                                       "details": None, "request_id": getattr(request.state, "request_id", None)}},
                )
        return await call_next(request)


def configure_tracing(app) -> None:
    if not settings.otel_enabled:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    log.info("otel_tracing_enabled", extra={"endpoint": settings.otel_exporter_otlp_endpoint})
