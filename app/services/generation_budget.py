"""Durable global reservations; never refund an uncertain provider invocation."""

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import text

from app.config.settings import settings
from app.core.errors import AppError, ErrorCode
from app.db.session import AsyncSessionLocal


# PostgreSQL serializes conflicting inserts/updates on the UTC day's primary key.
# The WHERE is evaluated against the locked row, not a prior application read.
RESERVE = text("""
    INSERT INTO generation_budgets (day, used)
    VALUES ((statement_timestamp() AT TIME ZONE 'UTC')::date, 1)
    ON CONFLICT (day) DO UPDATE
    SET used = generation_budgets.used + 1
    WHERE generation_budgets.used < :limit
    RETURNING day
""")


async def reserve_generation() -> None:
    limit = settings.ai_daily_generation_limit
    if limit == 0:
        raise AppError(
            ErrorCode.GENERATION_PAUSED,
            "New AI generation is paused. Cached insights are still available.",
            status_code=503,
        )

    try:
        # Dedicated transaction: cache writes, cancellation, and provider errors
        # cannot roll back a reservation after this commit succeeds.
        async with AsyncSessionLocal() as session:
            day = (
                await session.execute(RESERVE, {"limit": limit})
            ).scalar_one_or_none()
            if day is None:
                # Use the database clock for the retry boundary as well.
                today = (
                    await session.execute(
                        text("SELECT (statement_timestamp() AT TIME ZONE 'UTC')::date")
                    )
                ).scalar_one()
            await session.commit()
    except Exception as exc:
        # Connection establishment can raise raw driver/OSError/timeout errors,
        # not only SQLAlchemyError. None may allow an unreserved provider call.
        raise AppError(
            ErrorCode.GENERATION_UNAVAILABLE,
            "AI generation is temporarily unavailable. Please try again later.",
            status_code=503,
        ) from exc

    if day is None:
        retry_at = datetime.combine(today + timedelta(days=1), time(), timezone.utc)
        raise AppError(
            ErrorCode.GENERATION_LIMIT_REACHED,
            "Today's AI generation limit has been reached. Try again after "
            f"{retry_at:%Y-%m-%d %H:%M UTC}. Cached insights are still available.",
            details={"retry_at": retry_at.isoformat()},
            status_code=429,
        )
