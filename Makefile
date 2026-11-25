.PHONY: check lint format-check types arch test

check: lint format-check types arch test

lint:
	uv run ruff check .

format-check:
	uv run ruff format --check .

types:
	uv run mypy

arch:
	uv run lint-imports

test:
	uv run pytest
