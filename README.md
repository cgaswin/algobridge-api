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

## Deploy (Render + Neon, free tiers)

1. Create a Neon project with only Postgres enabled, in the same region as Render (`render.yaml` uses `ohio`; change both if you pick another).
2. In Neon's **Connect** dialog, turn **Connection pooling off** and copy the direct connection string. It can be pasted as-is: `sslmode` and `channel_binding` are converted for asyncpg (`app/db/url.py`).
3. In Render, choose **New → Blueprint** and select this repo. Fill in `DATABASE_URL` and `GEMINI_API_KEY` when prompted.
4. Each start runs `alembic upgrade head`, then uvicorn on `$PORT` (`scripts/start.sh`).
5. Optional: set the repository variable `API_BASE_URL` (e.g. `https://algobridge-api.onrender.com`) to enable `.github/workflows/keep-warm.yml`. It pings `/health` every 10 minutes so the free instance doesn't sleep.

Problem data comes from LeetCode's public GraphQL endpoint (`LEETCODE_GRAPHQL_URL` overrides it). Premium problems return `422`, because LeetCode withholds their statements from anonymous requests.

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
    "problem": {
      "slug": "two-sum",
      "title": "Two Sum",
      "difficulty": "easy",
      "tags": ["Array", "Hash Table"]
    },
    "use_case": "...",
    "system_examples": ["System — how the problem appears there", "..."],
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
- Cached rows are regenerated when `GEMINI_MODEL` or the prompt version (`app/llm/prompts.py`) changes.
- The generation prompt lives in `app/llm/prompts.py` and is shared with `evals/`, so eval results reflect production.
- Runtime uses async DB driver; migrations are handled via Alembic configuration.