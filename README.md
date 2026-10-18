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

1. Create a Neon project with only Postgres enabled, in the same region as Render (`render.yaml` uses `singapore`; change both if you pick another).
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

## Global AI generation budget

`AI_DAILY_GENERATION_LIMIT` defaults to **100** (nonnegative integer). Set it to
**0** to pause new API generation. `AI_GENERATION_TIMEOUT_SECONDS` defaults to
**30** (positive, at most 300 seconds). Settings load at process startup: apply
changes to **every worker/replica and restart them**. The pause takes full effect
only when all old workers have stopped; already-reserved/in-flight calls may
finish. Use the same limit and database on all replicas. Different limits during
a rolling config change can permit reservations up to the largest active limit.

For `POST /api/v1/problems`:

- A current-version cache hit is returned before the budget check, including
  when paused or exhausted. Stale model/prompt-version rows are cache misses.
- After fetching/validating the LeetCode problem, a dedicated transaction makes
  one atomic PostgreSQL upsert into `generation_budgets`, keyed by the database's
  **UTC calendar date**. Concurrent workers contend on that day's primary key;
  the increment only succeeds below the configured limit. No process-local
  counters, Redis, proxy configuration, or auth setup are required.
- The reservation **commits before Gemini is invoked**, with no database
  transaction held during the network call. Errors, invalid output, timeout,
  cancellation, cache-save failure, and crashes never refund a committed slot.
  A crash after committing but before sending may waste a slot. If commit
  acknowledgement is uncertain, no provider call is made (the slot may still
  have committed). Persistence errors fail closed with a handled `503`.
- Usage survives worker restarts. A new UTC date gets a new row automatically;
  no reset job is needed. Existing daily rows are retained. Lowering the limit
  below today's usage stops further reservations; raising it permits the
  difference. Do not delete/edit usage rows to reset a deployment.
- Gemini has a finite HTTP timeout and an async wall-clock deadline. SDK retry
  attempts are explicitly **1** (initial request only), and automatic function
  calling is disabled. Each committed reservation permits at most one API
  `generate_content` invocation; a client retry is a new request requiring a new
  slot unless the result is now cached. Timeout cancellation cannot guarantee
  the provider has stopped processing a request already received.

Handled errors use the existing `{success:false, data:null, error:{code,
message, details}}` envelope (the extension displays `message`):

| HTTP | Code | Meaning |
| --- | --- | --- |
| 503 | `GENERATION_PAUSED` | New generation paused; cached insights available |
| 429 | `GENERATION_LIMIT_REACHED` | Exhausted; message and `details.retry_at` give next UTC midnight |
| 503 | `GENERATION_UNAVAILABLE` | Persistence unavailable; retry later |
| 504 | `LLM_FAILURE` | Generation timed out; reservation still counts |

This is an **API invocation budget, not a dollar hard cap**. Output/input token
costs vary, provider processing can outlive timeouts, and two concurrent cache
misses for the same problem can each consume a slot. Other applications, manual
provider calls, and the standalone `evals/` tooling are **not covered**; use a
separate evaluation key/project and provider-side billing controls. There is no
per-user fairness/authentication protection in this feature.

### Safe deployment and rollback

1. Stop/drain old application workers that do not enforce the budget before
   exposing new workers (a mixed old/new fleet is not globally protected).
2. Back up the database and run `uv run alembic upgrade head` against the intended
   database. Revision `0002_generation_budget` adds only `generation_budgets`.
   Existing cache rows are untouched. `scripts/start.sh` already runs migrations
   before starting the server; do not bypass it without migrating first.
3. Start every worker with the same database and settings. For a cautious rollout,
   start with `AI_DAILY_GENERATION_LIMIT=0`, verify existing cached URLs still work
   and uncached valid URLs return the handled pause, then set the desired limit
   and restart all workers. No actual generation is needed for the pause check.
4. Schema/migration failure prevents normal startup. If a table goes missing at
   runtime, uncached generation fails closed; cached reads can still succeed if
   their own tables/database are available. `/health` is not a budget-readiness
   check. Monitor handled errors and the `generation_budgets` rows.
5. To downgrade, stop all budget-aware workers first, then run
   `uv run alembic downgrade 0001_create_problem_cache_tables`. This drops only
   the budget table **and its usage history**, not the cache. Old application
   versions have no cap: keep generation inaccessible or use provider-side
   controls during rollback. Re-upgrading starts a fresh counter; never downgrade
   and re-upgrade as an ordinary restart or it can reopen today's quota.

### Disposable PostgreSQL integration check

Tests never need a real Gemini key and never call the provider. The PostgreSQL
check is opt-in, creates/drops a unique test schema, and checks concurrent
reservations, UTC-day separation with a non-UTC session timezone, persisted
failure/timeout usage, and a fresh OS process seeing the exhausted cap. Point it
**only at a disposable database**, never production:

```bash
# Example local disposable database (remove it after testing):
docker run -d --rm --name algobridge-budget-test \
  -e POSTGRES_PASSWORD=disposable -e POSTGRES_DB=budget_test \
  -p 127.0.0.1:55432:5432 postgres:17-alpine
GEMINI_API_KEY=test \
TEST_BUDGET_DATABASE_URL=postgresql+asyncpg://postgres:disposable@127.0.0.1:55432/budget_test \
  uv run pytest -q
# Migration smoke test, using the same disposable DB:
GEMINI_API_KEY=test \
DATABASE_URL=postgresql+asyncpg://postgres:disposable@127.0.0.1:55432/budget_test \
  uv run alembic upgrade head
# Use the same environment for downgrade 0001_create_problem_cache_tables and
# upgrade head to verify rollback/re-upgrade. Never do this on live usage data.
docker stop algobridge-budget-test
```

Without `TEST_BUDGET_DATABASE_URL`, the PostgreSQL integration test is skipped;
unit tests still run with `GEMINI_API_KEY=test uv run pytest -q`.

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