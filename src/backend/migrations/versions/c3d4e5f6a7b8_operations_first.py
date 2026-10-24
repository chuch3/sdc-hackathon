"""Operations-first integrations and planning events.

Revision ID: c3d4e5f6a7b8
Revises: 8b1d2c3e4f5a
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "8b1d2c3e4f5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("email", sa.String(length=254), nullable=True))
    op.create_table(
        "market_days",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("demand_multiplier", sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_market_day_date", "market_days", ["market_date"], unique=True)
    op.create_table(
        "pos_webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )


def downgrade() -> None:
    op.drop_table("pos_webhook_events")
    op.drop_index("uq_market_day_date", table_name="market_days")
    op.drop_table("market_days")
    op.drop_column("suppliers", "email")
