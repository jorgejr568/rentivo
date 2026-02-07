IMAGE_NAME   := billing-generator
CONTAINER    := billing

# --- Local development ---

.PHONY: install
install:
	python -m venv .venv
	.venv/bin/pip install -e .

.PHONY: run
run:
	.venv/bin/python -m billing

.PHONY: migrate
migrate:
	.venv/bin/python -c "from billing.db import initialize_db; initialize_db()"

.PHONY: regenerate-pdfs
regenerate-pdfs:
	.venv/bin/python -m billing.scripts.regenerate_pdfs

.PHONY: regenerate-pdfs-dry
regenerate-pdfs-dry:
	.venv/bin/python -m billing.scripts.regenerate_pdfs --dry-run

# --- Docker (standalone) ---

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) .

.PHONY: up
up:
	docker run -d --name $(CONTAINER) \
		--env-file .env \
		-p 2019:2019 \
		$(IMAGE_NAME)

.PHONY: down
down:
	docker rm -f $(CONTAINER) 2>/dev/null || true

.PHONY: restart
restart: down up

.PHONY: shell
shell:
	docker exec -it $(CONTAINER) bash

.PHONY: billing
billing:
	docker exec -it $(CONTAINER) python -m billing

.PHONY: docker-migrate
docker-migrate:
	docker exec $(CONTAINER) python -c "from billing.db import initialize_db; initialize_db()"

.PHONY: docker-regenerate
docker-regenerate:
	docker exec $(CONTAINER) python -m billing.scripts.regenerate_pdfs

.PHONY: logs
logs:
	docker logs -f $(CONTAINER)

.PHONY: health
health:
	curl -s -o /dev/null -w '%{http_code}' http://localhost:2019/

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
	docker compose exec billing bash

.PHONY: compose-billing
compose-billing:
	docker compose exec billing python -m billing

.PHONY: compose-migrate
compose-migrate:
	docker compose exec billing python -c "from billing.db import initialize_db; initialize_db()"

.PHONY: compose-regenerate
compose-regenerate:
	docker compose exec billing python -m billing.scripts.regenerate_pdfs

.PHONY: compose-logs
compose-logs:
	docker compose logs -f
