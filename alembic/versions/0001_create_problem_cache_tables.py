"""create problem cache tables

Revision ID: 0001_create_problem_cache_tables
Revises:
Create Date: 2026-03-21 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_create_problem_cache_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "problems",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("canonical_key", sa.String(length=255), nullable=False),
        sa.Column("raw_url_first_seen", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "canonical_key",
            name="uq_problems_platform_key",
        ),
    )
    op.create_index("ix_problems_platform", "problems", ["platform"], unique=False)
    op.create_index("ix_problems_canonical_key", "problems", ["canonical_key"], unique=False)

    op.create_table(
        "problem_insights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("insights_json", sa.JSON(), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["problems.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("problem_id"),
    )
    op.create_index(
        "ix_problem_insights_problem_id",
        "problem_insights",
        ["problem_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_problem_insights_problem_id", table_name="problem_insights")
    op.drop_table("problem_insights")

    op.drop_index("ix_problems_canonical_key", table_name="problems")
    op.drop_index("ix_problems_platform", table_name="problems")
    op.drop_table("problems")
