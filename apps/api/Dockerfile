# DeployMind API. Build context: ./apps (so the assistant-service source is available to the deploy adapter).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 deploymind
WORKDIR /srv/api
COPY api/pyproject.toml ./
# Install dependencies first (cached layer), then the application itself.
RUN pip install --upgrade pip && python -c "import tomllib;print('\\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt && pip install -r /tmp/req.txt
COPY api/ ./
RUN pip install --no-deps .
COPY assistant-service/ /srv/assistant-service/
RUN mkdir -p /data/storage && chown -R deploymind /data /srv
USER deploymind
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD curl -fs http://127.0.0.1:8000/health || exit 1
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
