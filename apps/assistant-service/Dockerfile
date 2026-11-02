# Enterprise Knowledge Assistant runtime - the service DeployMind delivers to customers.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN useradd --create-home --uid 10001 assistant
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY service.py test_service.py ./
USER assistant
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8080"]
