from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utc_now


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("lead_time_days >= 0"),
        CheckConstraint("moq > 0"),
        CheckConstraint("reliability >= 0 AND reliability <= 1"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(254))
    lead_time_days: Mapped[int] = mapped_column(default=2)
    moq: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("1"))
    reliability: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.95"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("shelf_life_days > 0"),
        CheckConstraint("lead_time_days >= 0"),
        CheckConstraint("moq > 0"),
        CheckConstraint("case_size > 0"),
        CheckConstraint("review_period_days >= 0"),
        CheckConstraint("service_level >= 0.5 AND service_level <= 0.999"),
        CheckConstraint("safety_stock_days >= 0"),
        CheckConstraint("domain IN ('generic', 'bakery')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(50))
    unit: Mapped[str] = mapped_column(String(30))
    shelf_life_days: Mapped[int]
    storage_type: Mapped[str] = mapped_column(String(40), default="ambient")
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    lead_time_days: Mapped[int] = mapped_column(default=2)
    moq: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("1"))
    case_size: Mapped[int] = mapped_column(default=1)
    review_period_days: Mapped[int] = mapped_column(default=1)
    service_level: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.950"))
    safety_stock_days: Mapped[Decimal] = mapped_column(Numeric(8, 3), default=Decimal("1"))
    allergens: Mapped[list] = mapped_column(JSON, default=list)
    seasonal: Mapped[bool] = mapped_column(Boolean, default=False)
    domain: Mapped[str] = mapped_column(String(20), default="generic")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (
        CheckConstraint("quantity_received > 0"),
        CheckConstraint("quantity_remaining >= 0 AND quantity_remaining <= quantity_received"),
        CheckConstraint("unit_cost >= 0"),
        CheckConstraint("expiry_date >= received_date"),
        CheckConstraint("status IN ('ACTIVE', 'QUARANTINED', 'CLOSED')"),
        Index("uq_batch_product_code", "product_id", "batch_code", unique=True),
        Index("ix_batch_fefo", "product_id", "status", "expiry_date", "received_date", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    batch_code: Mapped[str] = mapped_column(String(80))
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    quantity_remaining: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    received_date: Mapped[date] = mapped_column(Date)
    baked_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta != 0"),
        CheckConstraint(
            "movement_type IN ('RECEIPT','SALE','WASTE','ADJUSTMENT','DONATION','TRANSFER')"
        ),
        Index("ix_movements_product_time", "product_id", "occurred_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(20))
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    daypart: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(300))
    actor_name: Mapped[str] = mapped_column(String(100), default="Demo Owner")
    request_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    stock_action_id: Mapped[int | None] = mapped_column(index=True)


class StockActionRequest(Base):
    __tablename__ = "stock_action_requests"
    __table_args__ = (
        CheckConstraint(
            "request_type IN ('STOCK_ACTION','ADJUSTMENT','PO_RECEIPT')"
        ),
        CheckConstraint("status IN ('APPLIED')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(100), unique=True)
    request_type: Mapped[str] = mapped_column(String(20))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"))
    canonical_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="APPLIED")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class StockoutEvent(Base):
    __tablename__ = "stockout_events"
    __table_args__ = (Index("ix_stockout_product_date", "product_id", "business_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    business_date: Mapped[date] = mapped_column(Date)
    daypart: Mapped[str | None] = mapped_column(String(20))
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    available_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(40), default="SALE_REJECTED")
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','APPROVED','RECEIVED','CANCELLED')"),
        Index("ix_purchase_supplier_status", "supplier_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    expected_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    approved_by: Mapped[str | None] = mapped_column(String(100))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        CheckConstraint("received_quantity >= 0 AND received_quantity <= quantity"),
        CheckConstraint("unit_cost >= 0"),
        Index("ix_po_line_product_order", "product_id", "purchase_order_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int]
    actor_name: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


# M4 owns the behaviour and any further migrations for these bakery tables.
class BreadProfile(Base):
    __tablename__ = "bread_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True)
    weekday_factors: Mapped[dict] = mapped_column(JSON, default=dict)
    daypart_shares: Mapped[dict] = mapped_column(JSON, default=dict)
    max_daily_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("200"))


class SeasonalIngredient(Base):
    __tablename__ = "seasonal_ingredients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    months_available: Mapped[list] = mapped_column(JSON, default=list)
    availability_score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    price_index: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    local: Mapped[bool] = mapped_column(Boolean, default=False)


class ProductionPlan(Base):
    __tablename__ = "production_plans"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','APPROVED','DONE','CANCELLED')"),
        Index("uq_production_slot", "plan_date", "product_id", "daypart", unique=True),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_date: Mapped[date] = mapped_column(Date)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    daypart: Mapped[str] = mapped_column(String(20))
    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    actual_baked: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    sold: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    discarded: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    approved_by: Mapped[str | None] = mapped_column(String(100))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class HolidayCalendar(Base):
    __tablename__ = "holiday_calendar"
    id: Mapped[int] = mapped_column(primary_key=True)
    holiday_date: Mapped[date] = mapped_column(Date, unique=True)
    label: Mapped[str] = mapped_column(String(100))
    demand_multiplier: Mapped[Decimal] = mapped_column(Numeric(8, 3))


class MarketDay(Base):
    """A locally configured trading event that lifts demand for one business day."""

    __tablename__ = "market_days"
    __table_args__ = (Index("uq_market_day_date", "market_date", unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    market_date: Mapped[date] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String(100))
    demand_multiplier: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    note: Mapped[str] = mapped_column(String(300), default="")


class PosWebhookEvent(Base):
    """Idempotency and audit record for externally submitted POS events."""

    __tablename__ = "pos_webhook_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(100), unique=True)
    event_type: Mapped[str] = mapped_column(String(20))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class SDGFactor(Base):
    __tablename__ = "sdg_factors"
    category: Mapped[str] = mapped_column(String(50), primary_key=True)
    kg_co2e_per_kg_waste: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    meals_per_kg_donated: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    source_note: Mapped[str] = mapped_column(String(300))
