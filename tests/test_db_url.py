import pytest

from app.db.url import async_database_url, sync_database_url

NEON = (
    "postgresql://user:p%40ss@ep-cool-1.us-east-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def test_async_url_converts_libpq_options():
    url = async_database_url(NEON)
    assert url.drivername == "postgresql+asyncpg"
    assert dict(url.query) == {"ssl": "require"}
    assert url.password == "p@ss"


def test_async_url_keeps_local_asyncpg_url():
    local = "postgresql+asyncpg://algobridge:algobridge@localhost:5432/algobridge"
    url = async_database_url(local)
    assert url.render_as_string(hide_password=False) == local


def test_async_url_accepts_postgres_scheme():
    assert async_database_url("postgres://u:p@h/db").drivername == "postgresql+asyncpg"


def test_sync_url_keeps_sslmode_for_psycopg():
    url = sync_database_url(NEON)
    assert url.drivername == "postgresql+psycopg"
    assert dict(url.query) == {"sslmode": "require", "channel_binding": "require"}


def test_sync_url_translates_asyncpg_ssl():
    url = sync_database_url("postgresql+asyncpg://u:p@h/db?ssl=require")
    assert dict(url.query) == {"sslmode": "require"}


def test_rejects_other_backends():
    with pytest.raises(ValueError):
        async_database_url("mysql://u:p@h/db")
