"""Opt-in real PostgreSQL checks. Uses a unique schema, never application tables.

GEMINI_API_KEY=test TEST_BUDGET_DATABASE_URL=postgresql+asyncpg://.../budget_test \
    uv run pytest tests/test_generation_budget_postgres.py -q
Only point this at a disposable local test database (CREATE SCHEMA required).
"""

import asyncio
import os
import subprocess
import sys
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import AppError, ErrorCode
from app.db.models import GenerationBudget
from app.llm import gemini
from app.services import generation_budget as budget
from app.services import problem_service
from app.platforms.leetcode import Problem

URL = os.environ.get("TEST_BUDGET_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires disposable PostgreSQL URL")


def test_postgres_atomic_durable_budget(monkeypatch):
    schema = "budget_test_" + uuid.uuid4().hex
    monkeypatch.setattr(budget.settings, "ai_daily_generation_limit", 7)

    async def run():
        admin = create_async_engine(URL)
        engine = create_async_engine(
            URL,
            connect_args={
                "server_settings": {
                    "search_path": schema,
                    "timezone": "Pacific/Honolulu",
                }
            },
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with admin.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            async with engine.begin() as conn:
                await conn.run_sync(GenerationBudget.__table__.create)
                # A full previous day must not block a fresh UTC day.
                await conn.execute(
                    text("""
                    INSERT INTO generation_budgets VALUES
                    ((statement_timestamp() AT TIME ZONE 'UTC')::date - 1, 100)
                """)
                )
            with patch.object(budget, "AsyncSessionLocal", factory):
                await budget.reserve_generation()  # below cap
                results = await asyncio.gather(
                    *(budget.reserve_generation() for _ in range(30)),
                    return_exceptions=True,
                )
                assert sum(r is None for r in results) == 6
                denied = [r for r in results if r is not None]
                assert len(denied) == 24
                assert all(
                    isinstance(r, AppError) and r.status_code == 429 for r in denied
                )
                async with factory() as session:
                    rows = (
                        await session.execute(
                            text(
                                "SELECT day, used FROM generation_budgets ORDER BY day"
                            )
                        )
                    ).all()
                assert [r.used for r in rows] == [100, 7]

                # Fresh OS process/new connection pool sees the committed cap.
                script = """
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.services import generation_budget as b
from app.core.errors import AppError
async def run():
    e = create_async_engine(os.environ['TEST_BUDGET_DATABASE_URL'],
        connect_args={'server_settings': {'search_path': os.environ['BUDGET_TEST_SCHEMA']}})
    b.AsyncSessionLocal = async_sessionmaker(e)
    try:
        await b.reserve_generation()
    except AppError as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError('Restart reopened quota')
    finally:
        await e.dispose()
asyncio.run(run())
"""
                env = {
                    **os.environ,
                    "BUDGET_TEST_SCHEMA": schema,
                    "AI_DAILY_GENERATION_LIMIT": "7",
                    "GEMINI_API_KEY": "test",
                }
                completed = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-c", script],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert completed.returncode == 0, completed.stderr

                # Observe committed usage on another connection *before* the
                # fake provider fails, then exercise the real async deadline.
                monkeypatch.setattr(budget.settings, "ai_daily_generation_limit", 9)
                monkeypatch.setattr(
                    budget.settings, "ai_generation_timeout_seconds", 0.01
                )
                for expected_used, status in ((8, 502), (9, 504)):

                    async def fail_generation(problem):
                        async with factory() as session:
                            used = (
                                await session.execute(
                                    text(
                                        "SELECT used FROM generation_budgets WHERE day = "
                                        "(statement_timestamp() AT TIME ZONE 'UTC')::date"
                                    )
                                )
                            ).scalar_one()
                        assert used == expected_used
                        if status == 502:
                            raise AppError(
                                ErrorCode.LLM_FAILURE,
                                "provider failed",
                                status_code=502,
                            )

                        async def hang(**kwargs):
                            await asyncio.sleep(10)

                        with patch.object(
                            gemini.client.aio.models,
                            "generate_content",
                            AsyncMock(side_effect=hang),
                        ):
                            return await gemini.generate_insights(problem)

                    with (
                        patch.object(problem_service, "AsyncSessionLocal", factory),
                        patch.object(
                            problem_service,
                            "get_cached_insights_by_key",
                            AsyncMock(return_value=None),
                        ),
                        patch.object(
                            problem_service,
                            "fetch_problem",
                            AsyncMock(
                                return_value=Problem(
                                    title="Test",
                                    difficulty="Easy",
                                    description="Test",
                                    tags=[],
                                )
                            ),
                        ),
                        patch.object(
                            problem_service,
                            "generate_insights",
                            AsyncMock(side_effect=fail_generation),
                        ) as generate,
                    ):
                        with pytest.raises(AppError) as exc:
                            await problem_service.analyze_problem(
                                "https://leetcode.com/problems/test/"
                            )
                        assert exc.value.status_code == status
                        generate.assert_awaited_once()
                with pytest.raises(AppError) as exc:
                    await budget.reserve_generation()
                assert exc.value.status_code == 429
                monkeypatch.setattr(budget.settings, "ai_daily_generation_limit", 0)
                with pytest.raises(AppError) as paused:
                    await budget.reserve_generation()
                assert paused.value.code == ErrorCode.GENERATION_PAUSED
                async with factory() as session:
                    assert (
                        await session.execute(
                            text(
                                "SELECT max(used) FROM generation_budgets WHERE day = "
                                "(statement_timestamp() AT TIME ZONE 'UTC')::date"
                            )
                        )
                    ).scalar_one() == 9

                # Missing migration/table is a handled closed gate, not permission
                # to call the provider. This touches only this test's schema.
                monkeypatch.setattr(budget.settings, "ai_daily_generation_limit", 100)
                async with engine.begin() as conn:
                    await conn.execute(text("DROP TABLE generation_budgets"))
                with pytest.raises(AppError) as unavailable:
                    await budget.reserve_generation()
                assert unavailable.value.code == ErrorCode.GENERATION_UNAVAILABLE
                assert unavailable.value.status_code == 503
        finally:
            await engine.dispose()
            async with admin.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(run())
