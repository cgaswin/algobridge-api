# AlgoBridge API

FastAPI backend for turning coding problem URLs into real-world engineering insights, with PostgreSQL caching to reduce repeated upstream calls.

## Features

- Analyze LeetCode problem URLs via `POST /api/v1/problems`
- Configurable, bounded per-IP incoming request limiting
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

## Incoming request limits

`POST /api/v1/problems` allows **60 requests per 60 seconds per IP** by default.
Every attempt counts (including cache hits and invalid requests), before body parsing
or any database, LeetCode, or Gemini work. `/health`, other routes, and CORS
preflight requests are not limited. The trailing-slash form is also counted.

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `RATE_LIMIT_REQUESTS` | `60` | Requests allowed in each IP's fixed window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window duration, starting on that IP's first request |
| `RATE_LIMIT_MAX_IPS` | `10000` | Maximum simultaneously tracked IP windows per process |

All three must be positive integers; invalid values fail application startup.
Set them in `.env` for local runs or in the deployment environment. Compose passes
these settings through. Tune against legitimate traffic and upstream capacity;
users sharing a school, office, VPN, or carrier NAT share one quota. Raising the
limit reduces shared-IP false positives but also weakens abuse protection.
Fixed windows allow bursts on both sides of a window boundary.

Rejections return `429`, a `Retry-After` header containing whole seconds (rounded
up, minimum 1), and the standard envelope:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests. Please retry later.",
    "details": {}
  }
}
```

State is bounded and **process-local**, not persistent: restarts clear quotas and
multiple workers/instances each allow their own quota. Expired windows are removed
on the next limited request. At the IP capacity, new IPs receive the same `429`
until the earliest tracked window expires; existing IPs retain their quotas.
Live entries are not evicted, so cycling new IPs cannot reset existing limits, but
an attacker can exhaust capacity and temporarily deny new users. IPs are kept in
memory only by this limiter; unknown/non-IP peers share a single fallback bucket.
This is a basic first-stage safeguard, not authentication, a distributed limit, or
a global persistent AI-spend budget. Clients able to rotate IPs can bypass a
per-IP quota. No new infrastructure is required.

### Proxy trust boundary (confirm before production rollout)

The limiter uses the ASGI client address, **not raw `X-Forwarded-For` or `Forwarded`
headers**. Uvicorn can rewrite that address, so server configuration is part of the
security boundary. `scripts/start.sh` and the Makefile now default
`FORWARDED_ALLOW_IPS` to empty (trust no forwarding headers), replacing the previous
trust-all `*`. The startup script rejects wildcard values; application settings
also reject invalid IPs/CIDRs and universal `/0` ranges.

For a verified reverse proxy, set `FORWARDED_ALLOW_IPS` in the **server process
environment** to a comma-separated list of its actual connecting IPs/CIDRs.
For example, `FORWARDED_ALLOW_IPS=10.20.30.4,10.20.31.0/24` is illustrative only,
not a Render setting. Uvicorn walks XFF right-to-left past trusted proxies to find
the client. Ensure each trusted proxy replaces or appends the real peer address,
not merely passes through a client-supplied header; trust only the specific proxy
hops, not arbitrary clients on a broad network. Never use `*`, `0.0.0.0/0`, or
`::/0`. If launching Uvicorn yourself, explicitly pass
`--forwarded-allow-ips="$FORWARDED_ALLOW_IPS"` (empty when unset).

**Render's actual proxy peer ranges and header sanitization have not been verified
in this repository.** Before claiming effective per-client protection, confirm:

1. The immediate proxy peer addresses/ranges and all intermediate trusted hops.
2. That the edge appends/replaces XFF with the real client, and direct access cannot
   spoof a trusted hop. Confirm using controlled requests with forged XFF values.
3. That two real external IPs receive independent quotas after configuration.

With the safe empty default behind a proxy, callers sharing a proxy address share
its quota; this may produce widespread `429`s. Do not solve that by blindly trusting
all forwarding headers. If stable, narrow proxy ranges cannot be established,
keep this limitation explicit and use a verified platform/edge limiter instead.
Set `FORWARDED_ALLOW_IPS` in Render's environment; merely adding it to `.env` does
not configure Uvicorn (Compose explicitly passes it, while `make` needs an exported
shell variable). Changing the startup setting also affects forwarded HTTPS scheme
handling; verify any scheme-dependent behavior at deployment.

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