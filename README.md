# AlgoBridge API

FastAPI backend for turning coding problem URLs into real-world engineering insights, with PostgreSQL caching to reduce repeated upstream calls.

## Features

- Analyze LeetCode problem URLs via `POST /api/v1/problems`
- Unified success/error response envelope
- PostgreSQL-backed insights cache
- Alembic migrations for schema management
- Dockerized local setup (API + Postgres)
- CORS configured for browser extension origins (`chrome-extension://`, `moz-extension://`)

## Tech Stack

- Python 3.13
- FastAPI
- SQLAlchemy (async runtime)
- Alembic
- PostgreSQL
- Docker / Docker Compose
- uv

## Quick Start

### 1) Install dependencies

```bash
uv sync
```

### 2) Configure environment

Create `.env` in project root:

```env
GEMINI_API_KEY=your_key
LEETCODE_ENDPOINT=http://localhost:3000
DATABASE_URL=postgresql+asyncpg://algobridge:algobridge@localhost:5432/algobridge
```

### 3) Start Postgres

```bash
docker compose up -d db
```

### 4) Run migrations

```bash
uv run alembic upgrade head
```

### 5) Start API

```bash
make dev
```

API will run on `http://localhost:8000`.

## Docker (API + DB)

```bash
docker compose up --build
```

## API

### Health

- `GET /health`

### Analyze Problem

- `POST /api/v1/problems`
- Body:

```json
{
  "url": "https://leetcode.com/problems/two-sum/"
}
```

- Success (`200`):

```json
{
  "success": true,
  "data": {
    "use_case": "...",
    "system_examples": "...",
    "explanation": "..."
  },
  "error": null
}
```

- Validation Error (`422`):

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INVALID_INPUT",
    "message": "Request validation failed",
    "details": []
  }
}
```

## Development Commands

```bash
make dev              # run with reload
make run              # run without reload
make migrate          # alembic upgrade head
make migrate-down     # alembic downgrade -1
make migrate-current  # show current migration revision
make test             # run tests
make lint             # ruff check
make format           # ruff format
```

## Notes

- Cache is keyed by canonical problem identity (not raw URL variants).
- Runtime uses async DB driver; migrations are handled via Alembic configuration.