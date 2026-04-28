SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
ENGINE_DIR := services/engine
UI_DIR := services/ui

.PHONY: help setup up down restart logs ps build pull \
        test test-engine test-ui lint fmt \
        smoke seed migrate backup clean \
        dev-engine

help:
	@echo "Common targets:"
	@echo "  make setup       - create data dirs with correct ownership (run once, as root)"
	@echo "  make up          - start the stack (engine, ui, fluent-bit, loki, grafana)"
	@echo "  make down        - stop the stack"
	@echo "  make restart     - restart the stack"
	@echo "  make logs        - tail logs for all services"
	@echo "  make build       - rebuild engine + ui images"
	@echo "  make test        - run engine + ui tests"
	@echo "  make smoke       - send a synthetic event end-to-end (requires running engine)"
	@echo "  make seed        - load seed filter rules into the engine"
	@echo "  make migrate     - run Alembic migrations inside the engine container"
	@echo "  make backup      - run the SQLite backup script"
	@echo "  make dev-engine  - run the engine locally without Docker (requires pip install)"

# loki runs as UID 10001; grafana runs as UID 472.
# Host directories must be owned by those UIDs so the containers can write to them.
setup:
	mkdir -p infra/data/engine infra/data/loki infra/data/grafana infra/data/raw-eve
	chown 10001:10001 infra/data/loki
	chown 472:472 infra/data/grafana

up: setup
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build engine ui

pull:
	$(COMPOSE) pull fluent-bit loki grafana

test: test-engine test-ui

test-engine:
	cd $(ENGINE_DIR) && python -m pytest -q

test-ui:
	cd $(UI_DIR) && python -m pytest -q

lint:
	cd $(ENGINE_DIR) && python -m ruff check app tests
	cd $(UI_DIR) && python -m ruff check app tests

fmt:
	cd $(ENGINE_DIR) && python -m ruff format app tests
	cd $(UI_DIR) && python -m ruff format app tests

smoke:
	bash tools/post_eve.sh services/engine/tests/fixtures/eve_alert_basic.json

seed:
	$(COMPOSE) exec engine python -m scripts.seed_filters

migrate:
	$(COMPOSE) exec engine alembic upgrade head

backup:
	bash infra/backups/sqlite-backup.sh

clean:
	$(COMPOSE) down -v
	rm -rf infra/data/engine/* infra/data/loki/* infra/data/grafana/* infra/data/raw-eve/*

# Run the engine directly with uvicorn — no Docker required.
# Reads ENGINE_API_TOKEN from the environment or .env.
# ENGINE_DB_PATH defaults to infra/data/engine/filters.db.
# Prerequisites: pip install -e services/engine
dev-engine:
	bash tools/dev-engine.sh
