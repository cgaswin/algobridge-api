import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import AppError, ErrorCode
from app.services import generation_budget as budget


def session_mock(day=date(2026, 4, 1)):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = day
    result.scalar_one.return_value = date(2026, 4, 1)
    session.execute.return_value = result
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    return factory, session


def test_reservation_commits():
    factory, session = session_mock()
    with patch.object(budget, "AsyncSessionLocal", factory):
        asyncio.run(budget.reserve_generation())
    session.commit.assert_awaited_once()
    assert session.execute.call_args.args[1] == {"limit": 100}


def test_exhausted_has_utc_retry():
    factory, session = session_mock(None)
    with patch.object(budget, "AsyncSessionLocal", factory):
        with pytest.raises(AppError) as exc:
            asyncio.run(budget.reserve_generation())
    assert exc.value.status_code == 429
    assert exc.value.details == {"retry_at": "2026-04-02T00:00:00+00:00"}
    session.commit.assert_awaited_once()


def test_zero_pauses_without_reservation(monkeypatch):
    monkeypatch.setattr(budget.settings, "ai_daily_generation_limit", 0)
    with patch.object(budget, "AsyncSessionLocal") as factory:
        with pytest.raises(AppError) as exc:
            asyncio.run(budget.reserve_generation())
    assert exc.value.code == ErrorCode.GENERATION_PAUSED
    assert exc.value.status_code == 503
    factory.assert_not_called()


@pytest.mark.parametrize("failure", ["execute", "commit"])
@pytest.mark.parametrize(
    "error",
    [SQLAlchemyError("DB unavailable"), OSError("connection refused"), TimeoutError()],
)
def test_persistence_failure_fails_closed(failure, error):
    factory, session = session_mock()
    getattr(session, failure).side_effect = error
    with patch.object(budget, "AsyncSessionLocal", factory):
        with pytest.raises(AppError) as exc:
            asyncio.run(budget.reserve_generation())
    assert exc.value.code == ErrorCode.GENERATION_UNAVAILABLE
    assert exc.value.status_code == 503
