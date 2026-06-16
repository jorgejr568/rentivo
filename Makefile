IMAGE_NAME     := rentivo-web
CONTAINER      := rentivo

PYTHON  := uv run python
UVICORN := uv run uvicorn
RUFF    := uv run ruff

# --- Local development ---

.PHONY: install
install:
	uv sync --all-extras
	uv run pre-commit install

.PHONY: migrate
migrate:
	$(PYTHON) -c "from rentivo.db import initialize_db; initialize_db()"

.PHONY: migrate-fresh
migrate-fresh:
	$(PYTHON) -c "\
from rentivo.db import get_engine; \
from sqlalchemy import text; \
e = get_engine(); \
conn = e.connect(); \
conn.execute(text('SET FOREIGN_KEY_CHECKS = 0')); \
tables = [r[0] for r in conn.execute(text('SHOW TABLES')).fetchall()]; \
[conn.execute(text(f'DROP TABLE \`{t}\`')) for t in tables]; \
conn.execute(text('SET FOREIGN_KEY_CHECKS = 1')); \
conn.commit(); conn.close(); \
print(f'Dropped {len(tables)} tables.'); \
from rentivo.db import initialize_db; initialize_db(); \
print('Migrations applied.')"

.PHONY: regenerate-pdfs
regenerate-pdfs:
	$(PYTHON) -m rentivo.scripts.regenerate_pdfs

.PHONY: regenerate-pdfs-dry
regenerate-pdfs-dry:
	$(PYTHON) -m rentivo.scripts.regenerate_pdfs --dry-run

.PHONY: backfill-encryption
backfill-encryption:
	$(PYTHON) -m rentivo.scripts.backfill_encryption

.PHONY: backfill-encryption-dry
backfill-encryption-dry:
	$(PYTHON) -m rentivo.scripts.backfill_encryption --dry-run

.PHONY: backfill-encryption-reset-blind-index
backfill-encryption-reset-blind-index:
	$(PYTHON) -m rentivo.scripts.backfill_encryption --reset-blind-index

.PHONY: redact-audit-logs
redact-audit-logs:
	$(PYTHON) -m rentivo.scripts.redact_audit_logs

.PHONY: redact-audit-logs-dry
redact-audit-logs-dry:
	$(PYTHON) -m rentivo.scripts.redact_audit_logs --dry-run

.PHONY: seed
seed:
	$(PYTHON) -m rentivo.scripts.seed

# --- Lint & Format ---

.PHONY: fmt
fmt:
	$(RUFF) format .
	$(RUFF) check --fix .

.PHONY: lint
lint:
	$(RUFF) check .
	$(RUFF) format --check .

# --- Tests ---

.PHONY: test
test:
	$(PYTHON) -m pytest -n auto

.PHONY: test-cov
test-cov:
	$(PYTHON) -m pytest -n auto --cov --cov-report=term-missing

# --- Web (local) ---

.PHONY: web-run
web-run:
	$(UVICORN) web.app:app --reload --port 8000

.PHONY: web-createuser
web-createuser:
	$(PYTHON) -c "from rentivo.db import initialize_db; initialize_db(); from rentivo.repositories.factory import get_user_repository; from rentivo.services.user_service import UserService; svc = UserService(get_user_repository()); username = input('Username: '); password = __import__('getpass').getpass('Password: '); svc.create_user(username, password); print(f'User {username} created.')"

# --- Worker (local) ---

.PHONY: worker
worker:
	$(PYTHON) -m rentivo.workers

# --- Docker: Web (standalone) ---

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) .

.PHONY: up
up:
	docker run -d --name $(CONTAINER) \
		--env-file .env \
		-p 8000:8000 \
		$(IMAGE_NAME)

.PHONY: down
down:
	docker rm -f $(CONTAINER) 2>/dev/null || true

.PHONY: restart
restart: down up

.PHONY: shell
shell:
	docker exec -it $(CONTAINER) bash

.PHONY: logs
logs:
	docker logs -f $(CONTAINER)

.PHONY: health
health:
	curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/

.PHONY: docker-migrate
docker-migrate:
	docker exec $(CONTAINER) python -c "from rentivo.db import initialize_db; initialize_db()"

.PHONY: docker-migrate-fresh
docker-migrate-fresh:
	docker exec $(CONTAINER) python -c "\
from rentivo.db import get_engine; \
from sqlalchemy import text; \
e = get_engine(); \
conn = e.connect(); \
conn.execute(text('SET FOREIGN_KEY_CHECKS = 0')); \
tables = [r[0] for r in conn.execute(text('SHOW TABLES')).fetchall()]; \
[conn.execute(text(f'DROP TABLE \`{t}\`')) for t in tables]; \
conn.execute(text('SET FOREIGN_KEY_CHECKS = 1')); \
conn.commit(); conn.close(); \
print(f'Dropped {len(tables)} tables.'); \
from rentivo.db import initialize_db; initialize_db(); \
print('Migrations applied.')"

.PHONY: docker-createuser
docker-createuser:
	docker exec -it $(CONTAINER) python -c "from rentivo.db import initialize_db; initialize_db(); from rentivo.repositories.factory import get_user_repository; from rentivo.services.user_service import UserService; svc = UserService(get_user_repository()); username = input('Username: '); password = __import__('getpass').getpass('Password: '); svc.create_user(username, password); print(f'User {username} created.')"

.PHONY: docker-regenerate
docker-regenerate:
	docker exec $(CONTAINER) python -m rentivo.scripts.regenerate_pdfs

# --- Docker: Worker (standalone) ---

IMAGE_NAME_WORKER := rentivo-worker
CONTAINER_WORKER  := rentivo-worker

.PHONY: build-worker
build-worker:
	docker build -f Dockerfile.worker -t $(IMAGE_NAME_WORKER) .

.PHONY: up-worker
up-worker:
	docker run -d --name $(CONTAINER_WORKER) \
		--env-file .env \
		$(IMAGE_NAME_WORKER)

.PHONY: down-worker
down-worker:
	docker rm -f $(CONTAINER_WORKER) 2>/dev/null || true

.PHONY: logs-worker
logs-worker:
	docker logs -f $(CONTAINER_WORKER)

.PHONY: shell-worker
shell-worker:
	docker exec -it $(CONTAINER_WORKER) bash

# --- Docker Compose ---

.PHONY: compose-up
compose-up:
	docker compose up -d --build

.PHONY: compose-down
compose-down:
	docker compose down

.PHONY: compose-restart
compose-restart:
	docker compose down
	docker compose up -d --build

.PHONY: compose-dev
compose-dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

.PHONY: compose-dev-down
compose-dev-down:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

.PHONY: compose-shell
compose-shell:
	docker compose exec rentivo bash

.PHONY: compose-worker
compose-worker:
	docker compose up -d --build worker

.PHONY: compose-logs-worker
compose-logs-worker:
	docker compose logs -f worker

.PHONY: compose-migrate
compose-migrate:
	docker compose exec rentivo python -c "from rentivo.db import initialize_db; initialize_db()"

.PHONY: compose-migrate-fresh
compose-migrate-fresh:
	docker compose exec rentivo python -c "\
from rentivo.db import get_engine; \
from sqlalchemy import text; \
e = get_engine(); \
conn = e.connect(); \
conn.execute(text('SET FOREIGN_KEY_CHECKS = 0')); \
tables = [r[0] for r in conn.execute(text('SHOW TABLES')).fetchall()]; \
[conn.execute(text(f'DROP TABLE \`{t}\`')) for t in tables]; \
conn.execute(text('SET FOREIGN_KEY_CHECKS = 1')); \
conn.commit(); conn.close(); \
print(f'Dropped {len(tables)} tables.'); \
from rentivo.db import initialize_db; initialize_db(); \
print('Migrations applied.')"

.PHONY: compose-createuser
compose-createuser:
	docker compose exec -it rentivo python -c "from rentivo.db import initialize_db; initialize_db(); from rentivo.repositories.factory import get_user_repository; from rentivo.services.user_service import UserService; svc = UserService(get_user_repository()); username = input('Username: '); password = __import__('getpass').getpass('Password: '); svc.create_user(username, password); print(f'User {username} created.')"

.PHONY: compose-regenerate
compose-regenerate:
	docker compose exec rentivo python -m rentivo.scripts.regenerate_pdfs

.PHONY: compose-logs
compose-logs:
	docker compose logs -f

.PHONY: jaeger-up
jaeger-up:
	docker compose --profile observability up -d jaeger
	@echo "Jaeger UI: http://localhost:16686"
	@echo "Set RENTIVO_OTEL_ENABLED=true and RENTIVO_OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 (compose) to send traces."

.PHONY: jaeger-down
jaeger-down:
	docker compose --profile observability stop jaeger

.PHONY: temporal-up
temporal-up:
	docker compose --profile temporal up -d temporal temporal-ui
	@echo "Temporal UI at http://localhost:8233 — set RENTIVO_JOB_BACKEND=temporal and RENTIVO_TEMPORAL_HOST=temporal:7233 (compose) or localhost:7233 (host)."

.PHONY: temporal-down
temporal-down:
	docker compose --profile temporal stop temporal temporal-ui
