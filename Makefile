dev:
	uv run fastapi dev app/main.py

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint format