FROM python:3.10

RUN apt-get update && apt-get install -y \
    default-mysql-client \
    libmariadb-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -e .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

CMD ["sh", "-c", "python -c 'from landlord.db import initialize_db; initialize_db()' && uvicorn web.app:app --host 0.0.0.0 --port 8000"]
