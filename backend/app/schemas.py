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
    safety_stock_days: NonnegativeQuantity = Decimal("1")
    allergens: list[str] = Field(default_factory=list)
    seasonal: bool = False
    domain: Literal["generic", "bakery"] = "generic"


class ProductOutput(ProductInput):
    id: int
    active: bool


class Actor(Schema):
    actor_name: str = Field(min_length=1, max_length=100)
    actor_role: Literal["owner", "bookkeeper", "viewer"] = "owner"
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


class Recommendation(Schema):
    product_id: int
    action: Literal["BUY", "HOLD", "REDUCE", "MARKDOWN", "DONATE", "BAKE"]
    quantity: NonnegativeQuantity
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    expiry_risk: str
    forecast_horizon_days: int = Field(gt=0)


class StockActionInput(Actor):
    product_id: int = Field(gt=0)
    quantity: Quantity
    request_id: str = Field(min_length=3, max_length=100)
    movement_type: Literal["SALE", "WASTE", "DONATION"]
    daypart: Literal["morning", "midday", "afternoon", "evening"] | None = None
