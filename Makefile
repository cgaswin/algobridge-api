dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint format
