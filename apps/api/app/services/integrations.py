"""Integration connectors with connection testing, sync, retry policies and run history.

Credentials are resolved server-side from the encrypted secret store at call time and never returned.
Outbound URLs are checked against SSRF rules (cloud metadata ranges are always blocked; private ranges are
blocked in production unless explicitly allow-listed).
"""

import hashlib
import hmac
import ipaddress
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import psycopg
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.secrets import read_secret
from app.models import Contact, Document, Integration, IntegrationRun
from app.rag.parsing import safe_filename
from app.rag.storage import get_storage, object_key

KINDS = {
    "rest_api": {"label": "REST API", "config": ["base_url", "health_path", "auth_header"]},
    "webhook": {"label": "Inbound webhook", "config": []},
    "postgres": {"label": "PostgreSQL", "config": ["host", "port", "database", "user", "query", "sslmode"]},
    "crm": {"label": "CRM", "config": ["base_url"]},
    "ticketing": {"label": "Ticketing", "config": ["base_url"]},
    "document_store": {"label": "Document store", "config": ["base_url", "app_id"]},
}


class ConnectorError(Exception):
    pass


@dataclass
class ConnectorResult:
    message: str
    records: int = 0


def check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ConnectorError("URL must be http(s) with a host")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 80)
    except socket.gaierror as exc:
        raise ConnectorError(f"Cannot resolve host {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_link_local or ip in ipaddress.ip_network("169.254.0.0/16"):
            raise ConnectorError("Link-local / cloud metadata addresses are not allowed")
        if settings.is_production and (ip.is_private or ip.is_loopback):
            raise ConnectorError("Private network addresses are not allowed in production")


def _secret(db: Session, integ: Integration) -> str | None:
    return read_secret(db, integ.organisation_id, integ.credential_secret_id) if integ.credential_secret_id else None


def _http(db: Session, integ: Integration) -> httpx.Client:
    base = integ.config.get("base_url", "")
    check_url(base)
    headers = {}
    token = _secret(db, integ)
    if token:
        headers[integ.config.get("auth_header") or "Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=base.rstrip("/"), headers=headers, timeout=10)


def _get_json(client: httpx.Client, path: str):
    r = client.get(path)
    if r.status_code >= 400:
        raise ConnectorError(f"GET {path} returned HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _test(db: Session, integ: Integration) -> ConnectorResult:
    if integ.kind == "postgres":
        return ConnectorResult(_pg(db, integ, test_only=True)[0])
    if integ.kind == "webhook":
        if not integ.credential_secret_id:
            raise ConnectorError("Webhook signing secret is not configured")
        return ConnectorResult(f"Ready to receive signed events at /api/v1/webhooks/{integ.id}")
    with _http(db, integ) as c:
        path = integ.config.get("health_path") or "/health"
        body = _get_json(c, path)
        return ConnectorResult(f"GET {path} OK: {str(body)[:200]}")


def _sync(db: Session, integ: Integration) -> ConnectorResult:
    if integ.kind == "postgres":
        msg, n = _pg(db, integ, test_only=False)
        return ConnectorResult(msg, n)
    if integ.kind == "crm":
        with _http(db, integ) as c:
            contacts = _get_json(c, "/contacts")["items"]
        existing = {e for e in db.scalars(select(Contact.email).where(Contact.organisation_id == integ.organisation_id))}
        new = 0
        for item in contacts:
            if item.get("email") and item["email"] not in existing:
                db.add(Contact(organisation_id=integ.organisation_id, full_name=item["name"], email=item["email"],
                               job_title=item.get("title"), notes=f"Imported from {integ.name}"))
                new += 1
        return ConnectorResult(f"Fetched {len(contacts)} CRM contacts; imported {new} new", len(contacts))
    if integ.kind == "ticketing":
        with _http(db, integ) as c:
            tickets = _get_json(c, "/tickets")["items"]
        open_n = sum(1 for t in tickets if t.get("status") == "open")
        return ConnectorResult(f"Fetched {len(tickets)} tickets ({open_n} open) for routing analysis", len(tickets))
    if integ.kind == "document_store":
        app_id = integ.config.get("app_id")
        if not app_id:
            raise ConnectorError("config.app_id (target knowledge assistant) is required for document sync")
        from app.workers.tasks import enqueue_ingest

        with _http(db, integ) as c:
            listing = _get_json(c, "/documents")["items"]
            known = set(db.scalars(select(Document.sha256).where(Document.organisation_id == integ.organisation_id)))
            created = 0
            for item in listing:
                r = c.get(f"/documents/{item['id']}/content")
                if r.status_code >= 400:
                    raise ConnectorError(f"Failed to download {item['id']}: HTTP {r.status_code}")
                data = r.content
                sha = hashlib.sha256(data).hexdigest()
                if sha in known:
                    continue
                fname = safe_filename(item["filename"])
                key = object_key(integ.organisation_id, fname)
                get_storage().put(key, data)
                doc = Document(organisation_id=integ.organisation_id, app_id=uuid.UUID(app_id), kind="knowledge",
                               filename=fname, title=item.get("title") or fname, content_type="text/plain",
                               size_bytes=len(data), sha256=sha, storage_key=key, status="uploaded",
                               visibility=item.get("visibility", "organisation"))
                db.add(doc)
                db.flush()
                enqueue_ingest(db, doc)
                created += 1
        return ConnectorResult(f"Listed {len(listing)} documents; queued {created} new for ingestion", created)
    if integ.kind == "rest_api":
        with _http(db, integ) as c:
            body = _get_json(c, integ.config.get("sync_path") or integ.config.get("health_path") or "/health")
        n = len(body.get("items", [])) if isinstance(body, dict) else len(body) if isinstance(body, list) else 1
        return ConnectorResult(f"Fetched {n} record(s)", n)
    raise ConnectorError(f"Sync is not supported for {integ.kind}")


def _pg(db: Session, integ: Integration, test_only: bool) -> tuple[str, int]:
    cfg = integ.config
    host = cfg.get("host", "")
    check_url(f"http://{host}:{cfg.get('port', 5432)}")
    try:
        with psycopg.connect(host=host, port=int(cfg.get("port", 5432)), dbname=cfg.get("database"),
                             user=cfg.get("user"), password=_secret(db, integ) or "", connect_timeout=5,
                             sslmode=cfg.get("sslmode", "prefer")) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute("select count(*) from information_schema.tables where table_schema = 'public'")
                tables = cur.fetchone()[0]
                if test_only or not cfg.get("query"):
                    return f"Connected (read-only); {tables} public tables visible", 0
                cur.execute(cfg["query"])  # executed inside a READ ONLY transaction
                rows = cur.fetchmany(1000)
                return f"Read-only query returned {len(rows)} row(s)", len(rows)
    except psycopg.Error as exc:
        raise ConnectorError(f"PostgreSQL error: {str(exc).strip()[:300]}") from exc


def execute(db: Session, integ: Integration, kind: str) -> IntegrationRun:
    policy = {"max_attempts": 3, "backoff_seconds": 2, **(integ.retry_policy or {})}
    attempts, delay = 0, float(policy["backoff_seconds"])
    t0 = time.perf_counter()
    result, error = None, None
    while attempts < int(policy["max_attempts"]):
        attempts += 1
        try:
            result = _test(db, integ) if kind == "test" else _sync(db, integ)
            error = None
            break
        except (ConnectorError, httpx.HTTPError) as exc:
            error = str(exc) or exc.__class__.__name__
            if attempts < int(policy["max_attempts"]):
                time.sleep(delay)
                delay *= 2
        except AppError as exc:
            error = exc.message
            break
    now = datetime.now(UTC)
    run = IntegrationRun(organisation_id=integ.organisation_id, integration_id=integ.id, kind=kind,
                         status="failed" if error else "succeeded", attempts=attempts,
                         records_processed=result.records if result else 0,
                         latency_ms=int((time.perf_counter() - t0) * 1000),
                         message=result.message if result else "", error=error)
    db.add(run)
    if kind == "test":
        integ.last_tested_at = now
    else:
        integ.last_synced_at = now
    integ.health = "failing" if error else ("degraded" if attempts > 1 else "healthy")
    if not error and integ.status == "inventory":
        integ.status = "active"
    db.flush()
    return run


def verify_webhook(db: Session, integ: Integration, body: bytes, signature: str | None) -> bool:
    if not integ.credential_secret_id or not signature:
        return False
    secret = read_secret(db, integ.organisation_id, integ.credential_secret_id)
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def validate_config(kind: str, config: dict) -> dict:
    if kind not in KINDS:
        raise AppError(f"Unknown integration kind '{kind}'", code="invalid_integration")
    lowered = {k.lower() for k in config}
    if lowered & {"password", "api_key", "token", "secret", "apikey"}:
        raise AppError("Do not put credentials in config; use the credentials endpoint", code="secret_in_config")
    return config
