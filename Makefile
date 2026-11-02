.PHONY: help setup dev migrate seed test lint typecheck down clean

help:
	@echo "Township Operations Platform - Engineering Commands:"
	@echo "  make setup      - Install dependencies for backend and frontend"
	@echo "  make dev        - Spin up Docker Compose local development environment"
	@echo "  make migrate    - Execute Alembic database migrations"
	@echo "  make seed       - Seed idempotent synthetic township dataset"
	@echo "  make test       - Execute automated test suites (backend & infra)"
	@echo "  make lint       - Run Ruff and ESLint linters"
	@echo "  make typecheck  - Run Mypy and TypeScript type checks"
	@echo "  make down       - Tear down Docker Compose services and volumes"

setup:
	@echo "Installing backend dependencies..."
	cd services/api && pip install -r requirements-dev.txt
	@echo "Installing frontend dependencies..."
	cd apps/web && npm install

dev:
	docker compose up --build

migrate:
	cd services/api && alembic upgrade head

seed:
	python scripts/seed.py

test:
	@echo "Running backend test suite..."
	cd services/api && pytest -v --tb=short
	@echo "Running infrastructure test suite..."
	cd infra/cdk && pytest -v

lint:
	cd services/api && ruff check .
	cd apps/web && npm run lint

typecheck:
	cd services/api && mypy app
	cd apps/web && npm run build

down:
	docker compose down -v
