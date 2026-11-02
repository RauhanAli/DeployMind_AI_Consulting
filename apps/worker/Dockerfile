# DeployMind background worker (Celery + beat). Shares the API's domain code; build context: ./apps
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 deploymind
WORKDIR /srv/api
COPY api/pyproject.toml ./
# Install dependencies first (cached layer), then the application itself.
RUN pip install --upgrade pip && python -c "import tomllib;print('\\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt && pip install -r /tmp/req.txt
COPY api/ ./
RUN pip install --no-deps .
COPY assistant-service/ /srv/assistant-service/
RUN mkdir -p /data/storage && chown -R deploymind /data /srv
# The local Docker deployment adapter needs the Docker socket (mounted in docker-compose).
# Running as root keeps socket permissions simple in local demos; in production use a remote adapter (ECS).
CMD ["celery", "-A", "app.workers.celery_app", "worker", "-B", "-l", "info", "--concurrency", "2"]
