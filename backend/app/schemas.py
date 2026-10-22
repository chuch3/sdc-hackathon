from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
NonnegativeQuantity = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Name = Annotated[str, Field(min_length=1, max_length=150)]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)


class SupplierInput(Schema):
    name: Name
    lead_time_days: int = Field(default=2, ge=0)
    moq: Quantity = Decimal("1")
    reliability: Decimal = Field(default=Decimal("0.95"), ge=0, le=1, decimal_places=3)


class SupplierOutput(SupplierInput):
    id: int
    active: bool


class ProductInput(Schema):
    sku: str = Field(min_length=1, max_length=50)
    name: Name
    category: str = Field(min_length=1, max_length=50)
    unit: str = Field(min_length=1, max_length=30)
    shelf_life_days: int = Field(gt=0)
    storage_type: str = Field(default="ambient", min_length=1, max_length=40)
    supplier_id: int | None = Field(default=None, gt=0)
    lead_time_days: int = Field(default=2, ge=0)
    moq: Quantity = Decimal("1")
    case_size: int = Field(default=1, gt=0)
    review_period_days: int = Field(default=1, ge=0)
    service_level: Decimal = Field(default=Decimal("0.95"), ge=0.5, le=0.999, decimal_places=3)
    safety_stock_days: NonnegativeQuantity = Decimal("1")
    allergens: list[str] = Field(default_factory=list)
    seasonal: bool = False
    domain: Literal["generic", "bakery"] = "generic"


class ProductOutput(ProductInput):
    id: int
    active: bool


class Actor(Schema):
    actor_name: str = Field(min_length=1, max_length=100)
    actor_role: Literal[
        "owner", "manager", "bookkeeper", "baker", "staff", "viewer"
    ] = "owner"
    reason: str = Field(min_length=1, max_length=300)


class BatchInput(Actor):
    product_id: int = Field(gt=0)
    batch_code: str = Field(min_length=1, max_length=80)
    quantity_received: Quantity
    received_date: date
    baked_date: date | None = None
    expiry_date: date
    unit_cost: Money = Decimal("0")
    request_id: str = Field(min_length=3, max_length=100)

    @model_validator(mode="after")
    def check_dates(self):
        if self.expiry_date < self.received_date:
            raise ValueError("expiry_date must be on or after received_date")
        if self.baked_date and self.baked_date > self.received_date:
            raise ValueError("baked_date must be on or before received_date")
        return self


class BatchOutput(Schema):
    id: int
    product_id: int
    batch_code: str
    quantity_received: Decimal
    quantity_remaining: Decimal
    received_date: date
    baked_date: date | None
    expiry_date: date
    unit_cost: Decimal
    status: str


class BatchStatusInput(Actor):
    status: Literal["ACTIVE", "QUARANTINED"]


class MovementOutput(Schema):
    id: int
    product_id: int
    batch_id: int
    movement_type: str
    quantity_delta: Decimal
    occurred_at: datetime
    daypart: str | None
    reason: str
    actor_name: str
    request_id: str | None


class PurchaseLineInput(Schema):
    product_id: int = Field(gt=0)
    quantity: Quantity
    unit_cost: Money


class PurchaseOrderInput(Schema):
    supplier_id: int = Field(gt=0)
    expected_date: date
    lines: list[PurchaseLineInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_products(self):
        ids = [line.product_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Combine repeated product IDs into one line")
        return self


class PurchaseLineOutput(PurchaseLineInput):
    id: int
    received_quantity: Decimal


class PurchaseOrderOutput(Schema):
    id: int
    supplier_id: int
    expected_date: date
    status: str
    created_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    lines: list[PurchaseLineOutput]


class OnOrderOutput(Schema):
    product_id: int
    as_of: date
    through: date | None
    quantity: Decimal
    overdue_quantity: Decimal


class StockActionInput(Actor):
    product_id: int = Field(gt=0)
    quantity: Quantity
    request_id: str = Field(min_length=3, max_length=100)
    movement_type: Literal["SALE", "WASTE", "DONATION"]
    daypart: Literal["morning", "midday", "afternoon", "evening"] | None = None


class StockAllocation(Schema):
    batch_id: int
    batch_code: str
    expiry_date: date
    quantity: Decimal
    unit_cost: Decimal


class StockActionOutput(Schema):
    request_id: str
    product_id: int
    movement_type: str
    requested_quantity: Decimal
    allocated_quantity: Decimal
    business_date: date
    status: str
    allocations: list[StockAllocation]
    replayed: bool = False


class StockAdjustmentInput(Actor):
    product_id: int = Field(gt=0)
    batch_id: int = Field(gt=0)
    quantity_delta: Decimal = Field(max_digits=14, decimal_places=3)
    request_id: str = Field(min_length=3, max_length=100)

    @model_validator(mode="after")
    def non_zero(self):
        if self.quantity_delta == 0:
            raise ValueError("quantity_delta must not be zero")
        return self


class PurchaseReceiptLineInput(Schema):
    purchase_order_line_id: int = Field(gt=0)
    quantity: Quantity
    received_date: date
    expiry_date: date
    baked_date: date | None = None
    batch_code: str | None = Field(default=None, min_length=1, max_length=80)
    unit_cost: Money | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.expiry_date < self.received_date:
            raise ValueError("expiry_date must be on or after received_date")
        if self.baked_date and self.baked_date > self.received_date:
            raise ValueError("baked_date must be on or before received_date")
        return self


class PurchaseReceiptInput(Actor):
    request_id: str = Field(min_length=3, max_length=100)
    lines: list[PurchaseReceiptLineInput] = Field(min_length=1, max_length=100)


class PurchaseReceiptOutput(Schema):
    request_id: str
    purchase_order_id: int
    status: str
    received_lines: int
    batches: list[BatchOutput]
    replayed: bool = False


class InventoryPositionOutput(Schema):
    product_id: int
    sku: str
    name: str
    category: str
    unit: str
    physical_on_hand: Decimal
    saleable_on_hand: Decimal
    expired_quantity: Decimal
    quarantined_quantity: Decimal
    on_order: Decimal
    overdue_on_order: Decimal
    earliest_expiry: date | None
    remaining_shelf_life_days: int
    risk_score: float
    buckets: dict[str, Decimal]


class ExpiryBucketItem(Schema):
    bucket: str
    product_id: int
    sku: str
    name: str
    batch_id: int
    batch_code: str
    quantity: Decimal
    unit_cost: Decimal
    value: Decimal
    expiry_date: date
    days_to_expiry: int
    remaining_shelf_life_days: int
    allowed_actions: list[str]


class ExpiryBucketOutput(Schema):
    as_of: date
    totals: dict[str, Decimal]
    value_at_risk: Decimal
    items: list[ExpiryBucketItem]


class ExpiryAlertOutput(Schema):
    as_of: date
    horizon_days: int
    alerts: list[ExpiryBucketItem]


class Recommendation(Schema):
    product_id: int
    sku: str = ""
    product_name: str = ""
    action: Literal["BUY", "HOLD", "REDUCE", "MARKDOWN", "DONATE", "BAKE", "WRITE_OFF"]
    quantity: NonnegativeQuantity
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    expiry_risk: str
    forecast_horizon_days: int = Field(gt=0)
    why: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    calculation: dict[str, float] = Field(default_factory=dict)
    model_name: str = ""
    model_version: str = ""
    forecast_run_id: str = ""
    input_snapshot_id: str = ""
    actionable: bool = True
    data_quality: dict | None = None
    forecast_lower: float = 0.0
    forecast_upper: float = 0.0
    approval_required: bool = True
    engine: str = "baseline"
    decision: str | None = None
    decided_at: datetime | None = None
    decided_by: str = ""


class RecommendationList(Schema):
    as_of: date
    engine: str
    recommendations: list[Recommendation]


class BreadProfileInput(Schema):
    weekday_factors: dict[str, float] = Field(default_factory=dict)
    daypart_shares: dict[str, float] = Field(default_factory=dict)
    max_daily_quantity: Quantity = Decimal("200")


class BreadProfileOutput(BreadProfileInput):
    product_id: int


class BakePlanSlot(Schema):
    daypart: str
    quantity: Decimal
    status: str = "DRAFT"


class BakePlanOutput(Schema):
    plan_date: date
    product_id: int
    sku: str
    product_name: str
    total_quantity: Decimal
    max_daily_quantity: Decimal
    slots: list[BakePlanSlot]
    reason: str
    approval_required: bool = True


class SeasonalAdvice(Schema):
    name: str
    availability_score: float
    price_index: float
    local: bool
    suggestion: str


class HolidayInput(Schema):
    holiday_date: date
    label: str = Field(min_length=1, max_length=100)
    demand_multiplier: Decimal = Field(gt=0, max_digits=8, decimal_places=3)


class HolidayOutput(HolidayInput):
    id: int


class BakePlanRequest(Actor):
    plan_date: date
    product_id: int = Field(gt=0)


class RecommendationDecisionInput(Actor):
    decision: Literal["APPROVED", "EDITED", "REJECTED"]
    action: Literal["BUY", "HOLD", "REDUCE", "MARKDOWN", "DONATE", "BAKE", "WRITE_OFF"]
    quantity: NonnegativeQuantity
    edited_quantity: NonnegativeQuantity | None = None
    note: str = Field(default="", max_length=300)


class PlannerCard(Schema):
    kind: Literal[
        "SELL_FIRST",
        "MARKDOWN",
        "DONATE",
        "WRITE_OFF",
        "RECEIVE_ORDER",
        "STOCKOUT",
        "BUY",
        "BAKE",
        "HOLD",
        "DATA_WARNING",
    ]
    priority: Literal["critical", "warning", "info"]
    product_id: int | None = None
    product_sku: str = ""
    product_name: str = ""
    quantity: NonnegativeQuantity = Decimal("0")
    unit: str = ""
    deadline: date | None = None
    summary: str = ""
    why: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.35, ge=0, le=1)
    expiry_risk: str = "healthy"
    impact: str = ""
    calculation: dict[str, float] = Field(default_factory=dict)


class PlannerOrderLine(Schema):
    product_id: int
    sku: str
    product_name: str
    quantity: NonnegativeQuantity
    unit_cost: Money = Decimal("0")
    expiry_date: date


class PlannerOrderDue(Schema):
    purchase_order_id: int
    supplier_id: int
    expected_date: date
    arrival_date: date
    overdue: bool = False
    total_quantity: NonnegativeQuantity = Decimal("0")
    lines: list[PlannerOrderLine] = Field(default_factory=list)


class PlannerDayKpis(Schema):
    value_at_risk: Money = Decimal("0")
    expected_waste: Money = Decimal("0")
    stockout_risk: Literal["low", "medium", "high"] = "low"


class PlannerProjection(Schema):
    starting_stock: NonnegativeQuantity = Decimal("0")
    arrivals: NonnegativeQuantity = Decimal("0")
    expected_sales: NonnegativeQuantity = Decimal("0")
    unmet_demand: NonnegativeQuantity = Decimal("0")
    ending_stock: NonnegativeQuantity = Decimal("0")
    expired_quantity: NonnegativeQuantity = Decimal("0")


class PlannerDay(Schema):
    date: date
    weekday: str
    headline: str = ""
    risk_level: Literal["calm", "busy", "risky"] = "calm"
    kpis: PlannerDayKpis = Field(default_factory=PlannerDayKpis)
    cards: list[PlannerCard] = Field(default_factory=list)
    orders_due: list[PlannerOrderDue] = Field(default_factory=list)
    projection: PlannerProjection = Field(default_factory=PlannerProjection)


class PlannerBadge(Schema):
    code: str
    label: str
    earned: bool = False
    detail: str = ""


class PlannerWeeklySummary(Schema):
    days: int = 0
    cards: int = 0
    cost_at_risk: Money = Decimal("0")
    expected_waste: Money = Decimal("0")
    estimated_cost_avoided: Money = Decimal("0")
    stockout_days: int = 0
    waste_free_days: int = 0
    plan_coverage_days: int = 0
    quest_progress: float = Field(default=0.0, ge=0, le=1)


class PlannerWeek(Schema):
    as_of: date
    start_date: date
    end_date: date
    day_count: int = 7
    mode: Literal["forecast"] = "forecast"
    engine: str = "baseline"
    generated_at: datetime
    days: list[PlannerDay] = Field(default_factory=list)
    badges: list[PlannerBadge] = Field(default_factory=list)
    weekly_summary: PlannerWeeklySummary = Field(default_factory=PlannerWeeklySummary)
    assumptions: list[str] = Field(default_factory=list)
