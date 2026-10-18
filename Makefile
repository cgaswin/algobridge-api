dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --forwarded-allow-ips="$${FORWARDED_ALLOW_IPS:-}"

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --forwarded-allow-ips="$${FORWARDED_ALLOW_IPS:-}"

migrate:
	uv run alembic upgrade head

migrate-down:
	uv run alembic downgrade -1

migrate-current:
	uv run alembic current
