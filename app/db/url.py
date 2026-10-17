from sqlalchemy.engine import URL, make_url

# Options libpq understands but asyncpg rejects. Hosted Postgres providers such
# as Neon put these in the connection strings they hand out.
_LIBPQ_ONLY_OPTIONS = ("sslmode", "channel_binding")


def _with_driver(url: str, driver: str) -> URL:
    # Heroku-style "postgres://" is still common in provider dashboards.
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise ValueError(f"Unsupported database backend: {parsed.get_backend_name()}")
    return parsed.set(drivername=f"postgresql+{driver}")


def async_database_url(url: str) -> URL:
    """URL for the app's asyncpg engine, accepting libpq-style strings."""
    parsed = _with_driver(url, "asyncpg")
    query = dict(parsed.query)
    sslmode = query.get("sslmode")
    for option in _LIBPQ_ONLY_OPTIONS:
        query.pop(option, None)
    if sslmode and "ssl" not in query:
        query["ssl"] = sslmode
    return parsed.set(query=query)


def sync_database_url(url: str) -> URL:
    """URL for Alembic's psycopg engine; libpq takes `sslmode` as-is."""
    parsed = _with_driver(url, "psycopg")
    query = dict(parsed.query)
    ssl = query.pop("ssl", None)
    if ssl and "sslmode" not in query:
        query["sslmode"] = ssl
    return parsed.set(query=query)
