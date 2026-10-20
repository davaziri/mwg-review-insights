PYTHON ?= python3
VENV := backend/.venv
BIN := $(CURDIR)/$(VENV)/bin

.PHONY: install migrate dev dev-api dev-worker dev-web test build sync up down logs

## One-command local start: API on :8000, worker, and the web app on http://localhost:5173
dev: migrate
	@echo ""
	@echo "  Open http://localhost:5173   (Ctrl+C stops everything)"
	@echo ""
	@$(MAKE) --no-print-directory -j3 dev-api dev-worker dev-web

install: $(VENV)/.installed frontend/node_modules/.installed

$(VENV)/.installed: backend/pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e "backend[dev]"
	@# Chromium for PDF reports (skipped when CHROMIUM_PATH points at one already installed).
	@if [ -z "$$CHROMIUM_PATH" ]; then $(BIN)/python -m playwright install chromium; fi
	@touch $@

frontend/node_modules/.installed: frontend/package.json frontend/package-lock.json
	cd frontend && npm install --no-audit --no-fund
	@touch $@

## Apply database migrations and add the seed titles
migrate: install
	cd backend && $(BIN)/python -m app.cli init-db

dev-api:
	cd backend && $(BIN)/uvicorn app.main:app --reload --port 8000

dev-worker:
	cd backend && $(BIN)/python -m app.cli worker

dev-web:
	cd frontend && npm run dev

## Backend tests and frontend type check
test: install
	cd backend && $(BIN)/pytest
	cd frontend && npm run typecheck

build: install
	cd frontend && npm run build

## Sync now without the worker: `make sync` for every title, `make sync APP=3308200` for one
sync: migrate
	cd backend && $(BIN)/python -m app.cli sync $(if $(APP),--app-id $(APP),--all)

## Docker: build and start the app and worker on http://localhost:8000
up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f
