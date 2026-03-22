from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Problem(Base):
    __tablename__ = "problems"
    __table_args__ = (
        UniqueConstraint("platform", "canonical_key", name="uq_problems_platform_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    canonical_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    raw_url_first_seen: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    insight: Mapped[ProblemInsight | None] = relationship(
        back_populates="problem",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProblemInsight(Base):
    __tablename__ = "problem_insights"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    insights_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    problem: Mapped[Problem] = relationship(back_populates="insight")
