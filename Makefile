SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
ENGINE_DIR := services/engine
UI_DIR := services/ui

.PHONY: help up down restart logs ps build pull \
        test test-engine test-ui lint fmt \
        smoke seed migrate backup clean

help:
	@echo "Common targets:"
	@echo "  make up          - start the stack (engine, ui, fluent-bit, loki, grafana)"
	@echo "  make down        - stop the stack"
	@echo "  make restart     - restart the stack"
	@echo "  make logs        - tail logs for all services"
	@echo "  make build       - rebuild engine + ui images"
	@echo "  make test        - run engine + ui tests"
	@echo "  make smoke       - send a synthetic event end-to-end"
	@echo "  make seed        - load seed filter rules into the engine"
	@echo "  make migrate     - run Alembic migrations inside the engine container"
	@echo "  make backup      - run the SQLite backup script"

up:
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
