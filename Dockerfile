# --- Build stage: install deps into /app/.venv with uv ---
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (no project) so this layer caches across source edits.
COPY pyproject.toml uv.lock ./
RUN mkdir -p rentivo web && touch rentivo/__init__.py web/__init__.py
RUN uv sync --frozen --no-install-project --extra cache

# Install the project itself.
COPY . .
RUN uv sync --frozen --extra cache

# --- Runtime stage: slim image with only the venv + source ---
FROM python:3.14-slim

RUN useradd --system --uid 10001 --create-home --home-dir /home/appuser --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p /app/invoices && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
