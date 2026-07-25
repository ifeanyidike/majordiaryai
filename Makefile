# Major Dairy AI — dev runner
# Backend: FastAPI (uvicorn) · Frontend: Expo (Metro)
#
# Quick start:  make install  →  make migrate  →  make seed  →  make dev
#
# Note: the backend runs on :8010 (port 8000 is often taken). The frontend's
# EXPO_PUBLIC_API_URL in .env must match BACKEND_PORT — keep both at 8010, or
# override: `make dev BACKEND_PORT=8020` and update .env accordingly.

BACKEND_HOST ?= 0.0.0.0
BACKEND_PORT ?= 8010
METRO_PORT   ?= 8081
CORS_ORIGINS ?= http://localhost:$(METRO_PORT),http://localhost:19006,http://localhost:$(BACKEND_PORT)

VENV := backend/.venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

# cd into backend/ so pydantic finds backend/.env and the relative venv resolves.
BACKEND_CMD := cd backend && CORS_ORIGINS="$(CORS_ORIGINS)" \
	.venv/bin/uvicorn main:app --host $(BACKEND_HOST) --port $(BACKEND_PORT) --reload

.DEFAULT_GOAL := help
.PHONY: help run dev backend frontend ios android install install-backend \
        install-frontend migrate seed typecheck check stop

help: ## Show available targets
	@echo "Major Dairy AI — make targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

run: dev ## Alias for 'dev' — run backend + Metro together

dev: ## Run backend + Metro together (Ctrl-C stops both)
	@echo "▶ backend  http://localhost:$(BACKEND_PORT)"
	@echo "▶ metro    http://localhost:$(METRO_PORT)   (press i=iOS · a=Android · w=web)"
	@trap 'kill 0' INT TERM EXIT; \
	  ( $(BACKEND_CMD) ) & \
	  ( npx expo start ) & \
	  wait

backend: ## Run only the FastAPI backend (auto-reload)
	$(BACKEND_CMD)

frontend: ## Run only the Expo dev server (Metro)
	npx expo start

ios: ## Run Metro and open the iOS simulator
	npx expo start --ios

android: ## Run Metro and open an Android emulator
	npx expo start --android

install: install-backend install-frontend ## Install backend + frontend dependencies

install-backend: ## Install Python deps into backend/.venv
	$(PIP) install -r backend/requirements.txt

install-frontend: ## Install JS dependencies (npm)
	npm install

migrate: ## Apply database migrations (alembic upgrade head)
	cd backend && .venv/bin/alembic upgrade head

seed: ## Seed the database with demo herd data
	cd backend && .venv/bin/python -m scripts.seed

typecheck: ## Type-check the frontend (tsc) and compile the backend
	npx tsc --noEmit
	$(PY) -m compileall -q backend/app backend/main.py

check: typecheck ## Alias for typecheck

stop: ## Stop backend + Metro by port (won't touch other uvicorn apps)
	-@lsof -ti tcp:$(BACKEND_PORT) | xargs kill 2>/dev/null || true
	-@lsof -ti tcp:$(METRO_PORT)  | xargs kill 2>/dev/null || true
	@echo "stopped :$(BACKEND_PORT) and :$(METRO_PORT)"
