"""M2 inventory, FEFO requests, and expiry-supporting fields

Revision ID: 8b1d2c3e4f5a
Revises: 0c1773a1d629
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8b1d2c3e4f5a"
down_revision: Union[str, None] = "0c1773a1d629"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("case_size", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "products",
        sa.Column("review_period_days", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "products",
        sa.Column(
            "service_level",
            sa.Numeric(precision=4, scale=3),
            nullable=False,
            server_default="0.950",
        ),
    )

    op.create_table(
        "stock_action_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column("request_type", sa.String(length=20), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("purchase_order_id", sa.Integer(), nullable=True),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "request_type IN ('STOCK_ACTION','ADJUSTMENT','PO_RECEIPT')",
            name="ck_stock_action_request_type",
        ),
        sa.CheckConstraint("status IN ('APPLIED')", name="ck_stock_action_status"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    with op.batch_alter_table("stock_action_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stock_action_requests_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "stockout_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("daypart", sa.String(length=20), nullable=True),
        sa.Column("requested_quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("available_quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("stockout_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_stockout_product_date", ["product_id", "business_date"], unique=False
        )

    op.add_column("stock_movements", sa.Column("stock_action_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_stock_movements_stock_action_id",
        "stock_movements",
        ["stock_action_id"],
        unique=False,
    )
    op.create_index(
        "ix_movements_product_type_time",
        "stock_movements",
        ["product_id", "movement_type", "occurred_at"],
        unique=False,
    )

    op.add_column("purchase_orders", sa.Column("received_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("production_plans", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT")
        )
        batch_op.add_column(sa.Column("approved_by", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(), nullable=True))
        batch_op.create_check_constraint(
            "ck_production_plan_status",
            "status IN ('DRAFT','APPROVED','DONE','CANCELLED')",
        )


def downgrade() -> None:
    with op.batch_alter_table("production_plans", schema=None) as batch_op:
        batch_op.drop_constraint("ck_production_plan_status", type_="check")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by")
        batch_op.drop_column("status")

    op.drop_column("purchase_orders", "received_at")
    op.drop_index("ix_movements_product_type_time", table_name="stock_movements")
    op.drop_index("ix_stock_movements_stock_action_id", table_name="stock_movements")
    op.drop_column("stock_movements", "stock_action_id")

    with op.batch_alter_table("stockout_events", schema=None) as batch_op:
        batch_op.drop_index("ix_stockout_product_date")
    op.drop_table("stockout_events")

    with op.batch_alter_table("stock_action_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stock_action_requests_product_id"))
    op.drop_table("stock_action_requests")

    op.drop_column("products", "service_level")
    op.drop_column("products", "review_period_days")
    op.drop_column("products", "case_size")
