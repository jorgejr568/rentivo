FROM python:3.10

RUN apt-get update && apt-get install -y \
    default-mysql-client \
    libmariadb-dev \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -e . gunicorn

RUN cd web && python manage.py collectstatic --no-input

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

CMD ["sh", "-c", "cd web && python manage.py migrate --no-input && gunicorn landlord_web.wsgi:application --bind 0.0.0.0:8000"]
