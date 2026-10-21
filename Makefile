.PHONY: services dev bench ui e2e lint

services:
	docker compose up -d

lint:
	uv run ruff check .

dev:
	uv run uvicorn app.main:app --port 8000

bench:
	k6 run bench/k6.js

ui:
	cd frontend && npm ci && npm run build

e2e:
	bash scripts/run_e2e.sh
