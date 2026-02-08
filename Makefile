IMAGE_NAME     := landlord-web
IMAGE_NAME_CLI := landlord-cli
CONTAINER      := landlord
CONTAINER_CLI  := landlord-cli

PYTHON  := $(shell [ -d .venv ] && echo .venv/bin/python || echo python)
PIP     := $(shell [ -d .venv ] && echo .venv/bin/pip || echo pip)
UVICORN := $(shell [ -d .venv ] && echo .venv/bin/uvicorn || echo uvicorn)

# --- Local development ---

.PHONY: install
install:
	python -m venv .venv
	$(PIP) install -e .

.PHONY: run
run:
	$(PYTHON) -m landlord

.PHONY: migrate
migrate:
	$(PYTHON) -c "from landlord.db import initialize_db; initialize_db()"

.PHONY: regenerate-pdfs
regenerate-pdfs:
	$(PYTHON) -m landlord.scripts.regenerate_pdfs

.PHONY: regenerate-pdfs-dry
regenerate-pdfs-dry:
	$(PYTHON) -m landlord.scripts.regenerate_pdfs --dry-run

# --- Tests ---

.PHONY: test
test:
	$(PYTHON) -m pytest

.PHONY: test-cov
test-cov:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

# --- Web (local) ---

.PHONY: web-run
web-run:
	$(UVICORN) web.app:app --reload --port 8000

.PHONY: web-createuser
web-createuser:
	$(PYTHON) -c "from landlord.db import initialize_db; initialize_db(); from landlord.repositories.factory import get_user_repository; from landlord.services.user_service import UserService; svc = UserService(get_user_repository()); username = input('Username: '); password = __import__('getpass').getpass('Password: '); svc.create_user(username, password); print(f'User {username} created.')"

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
	docker exec $(CONTAINER) python -c "from landlord.db import initialize_db; initialize_db()"

.PHONY: docker-createuser
docker-createuser:
	docker exec -it $(CONTAINER) python -c "from landlord.db import initialize_db; initialize_db(); from landlord.repositories.factory import get_user_repository; from landlord.services.user_service import UserService; svc = UserService(get_user_repository()); username = input('Username: '); password = __import__('getpass').getpass('Password: '); svc.create_user(username, password); print(f'User {username} created.')"

.PHONY: docker-regenerate
docker-regenerate:
	docker exec $(CONTAINER) python -m landlord.scripts.regenerate_pdfs

# --- Docker: CLI (standalone) ---

.PHONY: build-cli
build-cli:
	docker build -f Dockerfile.cli -t $(IMAGE_NAME_CLI) .

.PHONY: up-cli
up-cli:
	docker run -d --name $(CONTAINER_CLI) \
		--env-file .env \
		-p 2019:2019 \
		$(IMAGE_NAME_CLI)

.PHONY: down-cli
down-cli:
	docker rm -f $(CONTAINER_CLI) 2>/dev/null || true

.PHONY: landlord
landlord:
	docker exec -it $(CONTAINER_CLI) python -m landlord

.PHONY: shell-cli
shell-cli:
	docker exec -it $(CONTAINER_CLI) bash

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

.PHONY: compose-shell
compose-shell:
	docker compose exec landlord bash

.PHONY: compose-shell-cli
compose-shell-cli:
	docker compose exec cli bash

.PHONY: compose-landlord
compose-landlord:
	docker compose exec cli python -m landlord

.PHONY: compose-migrate
compose-migrate:
	docker compose exec landlord python -c "from landlord.db import initialize_db; initialize_db()"

.PHONY: compose-createuser
compose-createuser:
	docker compose exec -it landlord python -c "from landlord.db import initialize_db; initialize_db(); from landlord.repositories.factory import get_user_repository; from landlord.services.user_service import UserService; svc = UserService(get_user_repository()); username = input('Username: '); password = __import__('getpass').getpass('Password: '); svc.create_user(username, password); print(f'User {username} created.')"

.PHONY: compose-regenerate
compose-regenerate:
	docker compose exec cli python -m landlord.scripts.regenerate_pdfs

.PHONY: compose-logs
compose-logs:
	docker compose logs -f
