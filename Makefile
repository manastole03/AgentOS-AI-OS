.PHONY: bootstrap dev demo up down format lint test test-integration typecheck build migrate seed-demo openapi kustomize helm terraform load-test job-watch-scan verify clean

bootstrap:
	corepack enable
	pnpm install --frozen-lockfile=false
	uv sync --all-packages --dev

dev:
	docker compose up --build

demo:
	docker compose up -d --build postgres redis api ai
	docker compose run --rm api healthos-seed-demo
	docker compose up -d --build

up:
	docker compose up -d --build

down:
	docker compose down --remove-orphans

format:
	pnpm format
	uv run ruff format .

lint:
	pnpm lint
	uv run ruff check .

test:
	pnpm test
	uv run pytest --cov --cov-report=term-missing

test-integration:
	RUN_INTEGRATION_TESTS=1 uv run pytest -m integration

typecheck:
	pnpm typecheck
	uv run mypy

build:
	pnpm build
	docker compose build

migrate:
	docker compose run --rm api alembic upgrade head
	docker compose run --rm ai alembic upgrade head

seed-demo: migrate
	docker compose run --rm api healthos-seed-demo

openapi:
	uv run python scripts/export_openapi.py

kustomize:
	kubectl kustomize infra/kubernetes/overlays/development >/dev/null
	kubectl kustomize infra/kubernetes/overlays/production >/dev/null

helm:
	helm lint deploy/helm/healthos
	helm template healthos deploy/helm/healthos --namespace healthos >/dev/null

terraform:
	terraform -chdir=infra/terraform/aws fmt -check -recursive
	terraform -chdir=infra/terraform/aws init -backend=false
	terraform -chdir=infra/terraform/aws validate

load-test:
	k6 run tests/load/healthos.js

job-watch-scan:
	docker compose run --rm job-watch-worker healthos-job-watch-scan

verify: lint typecheck test openapi kustomize helm terraform

clean:
	pnpm clean
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache
