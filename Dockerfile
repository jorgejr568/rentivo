# --- Build stage: install Python deps (all pure-Python) ---
FROM python:3.14-slim AS builder

WORKDIR /app

COPY pyproject.toml .
RUN mkdir -p rentivo web && touch rentivo/__init__.py web/__init__.py
RUN pip install --no-cache-dir '.[cache]'

COPY . .
RUN pip install --no-cache-dir '.[cache]'

# --- Runtime stage: slim image with only what's needed ---
FROM python:3.14-slim

RUN useradd --system --uid 10001 --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

RUN mkdir -p /app/invoices && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
