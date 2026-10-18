"""Persist daily global AI generation reservations.

Revision ID: 0002_generation_budget
Revises: 0001_create_problem_cache_tables
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_generation_budget"
down_revision = "0001_create_problem_cache_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_budgets",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.CheckConstraint("used >= 0", name="ck_generation_budget_used"),
    )


def downgrade() -> None:
    op.drop_table("generation_budgets")
