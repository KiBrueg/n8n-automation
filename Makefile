# ============================================================
# AI Automation Hub — удобные команды
# DEV  → docker-compose.yml
# PROD → docker-compose.prod.yml
# ============================================================

DC_DEV  := docker compose -f docker-compose.yml
DC_PROD := docker compose -f docker-compose.prod.yml

.DEFAULT_GOAL := help

.PHONY: help
help: ## показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------- DEV ----------
.PHONY: up down logs ps build
up: ## dev: поднять стек
	$(DC_DEV) up -d --build
down: ## dev: остановить стек
	$(DC_DEV) down
logs: ## dev: логи (follow)
	$(DC_DEV) logs -f --tail=100
ps: ## dev: статус
	$(DC_DEV) ps
build: ## dev: пересобрать gateway
	$(DC_DEV) build gateway

# ---------- PROD ----------
.PHONY: prod-up prod-down prod-logs prod-ps prod-config deploy backup
prod-up: ## prod: поднять стек
	$(DC_PROD) up -d --remove-orphans
prod-down: ## prod: остановить стек
	$(DC_PROD) down
prod-logs: ## prod: логи (follow)
	$(DC_PROD) logs -f --tail=100
prod-ps: ## prod: статус
	$(DC_PROD) ps
prod-config: ## prod: валидация compose-конфига
	$(DC_PROD) config >/dev/null && echo "OK: prod-конфиг валиден"
deploy: ## prod: git pull + pull + up (на сервере)
	./deploy/deploy.sh
backup: ## prod: бэкап Postgres
	./deploy/backup.sh

# ---------- QA ----------
.PHONY: lint test config-check
lint: ## gateway: ruff
	cd gateway && ruff check .
test: ## gateway: pytest
	cd gateway && PYTHONPATH=. pytest -q
config-check: ## валидация обоих compose-файлов
	$(DC_DEV) config >/dev/null && echo "dev OK"
	$(DC_PROD) config >/dev/null && echo "prod OK"
