from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Mapping, Sequence


class Domain(str, Enum):
    GENERIC = "generic"
    BAKERY = "bakery"


class Action(str, Enum):
    BUY = "BUY"
    BAKE = "BAKE"
    HOLD = "HOLD"
    MARKDOWN = "MARKDOWN"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReasonCode(str, Enum):
    BASELINE_28D = "BASELINE_28D_MEAN"
    WEEKDAY_FACTOR = "WEEKDAY_FACTOR_APPLIED"
    DAYPART_SHARE = "DAYPART_SHARE_APPLIED"
    HOLIDAY_OVERRIDE = "HOLIDAY_OVERRIDE_APPLIED"
    CENSORED_EXCLUDED = "CENSORED_STOCKOUTS_EXCLUDED"
    COLD_START = "COLD_START_CATEGORY_FALLBACK"
    LOW_HISTORY = "LOW_HISTORY"
    HIGH_VARIABILITY = "HIGH_VARIABILITY"
    NO_HISTORY = "NO_HISTORY"
    STALE_DATA = "STALE_DATA"
    NEAR_EXPIRY_SURPLUS = "NEAR_EXPIRY_SURPLUS"
    REORDER_POINT = "REORDER_POINT_BREACHED"
    NO_REORDER = "NO_REORDER_NEEDED"
    SHELF_LIFE_CAP = "SHELF_LIFE_CAP_APPLIED"
    MOQ_ROUNDED = "MOQ_ROUNDED"
    BLOCKED_DATA_QUALITY = "BLOCKED_DATA_QUALITY"
    ML_FORECAST = "ML_FORECAST"
    ML_FALLBACK_BASELINE = "ML_FALLBACK_BASELINE"
    ML_LOW_COVERAGE = "ML_LOW_COVERAGE"


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    category: str
    domain: Domain = Domain.GENERIC
    unit: str = "unit"
    shelf_life_days: int = 3
    lead_time_days: int = 1
    review_period_days: int = 1
    moq: int = 1
    case_size: int = 1
    safety_stock_days: float = 1.0
    service_level: float = 0.95
    weekday_factors: Mapping[int, float] = field(default_factory=dict)
    daypart_shares: Mapping[str, float] = field(default_factory=dict)
    near_expiry_threshold_days: int = 2


@dataclass(frozen=True)
class SalesObservation:
    product_sku: str
    business_date: date
    quantity: float
    daypart: str | None = None
    is_stockout_censored: bool = False


@dataclass(frozen=True)
class CalendarOverride:
    business_date: date
    multiplier: float
    product_sku: str | None = None
    kind: str = "holiday"


@dataclass(frozen=True)
class InventoryPosition:
    product_sku: str
    saleable_on_hand: float
    on_order: float = 0.0
    remaining_shelf_life_days: int = 99
    forecast_error: float | None = None


@dataclass(frozen=True)
class ForecastRequest:
    product_sku: str
    as_of_date: date
    horizon_days: int
    daypart: str | None = None
    forecast_run_id: str | None = None
    input_snapshot_id: str | None = None


@dataclass(frozen=True)
class ForecastContext:
    products: Mapping[str, Product]
    sales_history: Sequence[SalesObservation]
    overrides: Sequence[CalendarOverride] = ()


@dataclass(frozen=True)
class DataQuality:
    window_days: int
    history_days: int
    valid_days: int
    censored_days: int
    last_sale_date: date | None
    cold_start: bool
    stale: bool


@dataclass(frozen=True)
class DailyForecast:
    forecast_date: date
    quantity: float
    lower: float
    upper: float
    daypart: str | None = None


@dataclass(frozen=True)
class ForecastResult:
    product_sku: str
    as_of_date: date
    horizon_days: int
    daily: Sequence[DailyForecast]
    total_quantity: float
    total_lower: float
    total_upper: float
    error_std: float
    confidence: Confidence
    model_name: str
    model_version: str
    reason_codes: Sequence[ReasonCode]
    why: Sequence[str]
    data_quality: DataQuality
    forecast_run_id: str
    input_snapshot_id: str
    actionable: bool


@dataclass(frozen=True)
class Recommendation:
    product_sku: str
    product_name: str
    action: Action
    quantity: float
    rationale: str
    why: Sequence[str]
    confidence: Confidence
    reason_codes: Sequence[ReasonCode]
    expiry_risk: str
    forecast_horizon_days: int
    calculation: Mapping[str, float]
    forecast: ForecastResult
    shelf_forecast: ForecastResult | None
    forecast_run_id: str
    input_snapshot_id: str
    approval_required: bool = True
