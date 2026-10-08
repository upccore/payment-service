.PHONY: up down test test-unit lint format

up:
	docker compose up --build

down:
	docker compose down -v

test:
	pytest

test-unit:
	pytest -m "not integration"

lint:
	ruff check .
	ruff format --check .
	mypy app tests alembic/env.py

format:
	ruff check --fix .
	ruff format .
