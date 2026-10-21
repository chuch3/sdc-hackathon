from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .contracts import (
    CalendarOverride,
    Domain,
    InventoryPosition,
    Product,
    SalesObservation,
)
from .repository import InMemoryRepository


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_product(raw: dict[str, Any]) -> Product:
    return Product(
        sku=raw["sku"],
        name=raw["name"],
        category=raw["category"],
        domain=Domain(raw.get("domain", "generic")),
        unit=raw.get("unit", "unit"),
        shelf_life_days=int(raw.get("shelf_life_days", 3)),
        lead_time_days=int(raw.get("lead_time_days", 1)),
        review_period_days=int(raw.get("review_period_days", 1)),
        moq=int(raw.get("moq", 1)),
        case_size=int(raw.get("case_size", 1)),
        safety_stock_days=float(raw.get("safety_stock_days", 1.0)),
        service_level=float(raw.get("service_level", 0.95)),
        weekday_factors={
            int(key): float(value)
            for key, value in raw.get("weekday_factors", {}).items()
        },
        daypart_shares={
            str(key): float(value)
            for key, value in raw.get("daypart_shares", {}).items()
        },
        near_expiry_threshold_days=int(raw.get("near_expiry_threshold_days", 2)),
    )


def _parse_sales_observation(raw: dict[str, Any]) -> SalesObservation:
    return SalesObservation(
        product_sku=raw["product_sku"],
        business_date=_parse_date(raw["business_date"]),
        quantity=float(raw["quantity"]),
        daypart=raw.get("daypart"),
        is_stockout_censored=bool(raw.get("is_stockout_censored", False)),
    )


def _parse_inventory_position(raw: dict[str, Any]) -> InventoryPosition:
    error = raw.get("forecast_error")
    return InventoryPosition(
        product_sku=raw["product_sku"],
        saleable_on_hand=float(raw["saleable_on_hand"]),
        on_order=float(raw.get("on_order", 0.0)),
        remaining_shelf_life_days=int(raw.get("remaining_shelf_life_days", 99)),
        forecast_error=None if error is None else float(error),
    )


def _parse_override(raw: dict[str, Any]) -> CalendarOverride:
    return CalendarOverride(
        business_date=_parse_date(raw["business_date"]),
        multiplier=float(raw["multiplier"]),
        product_sku=raw.get("product_sku"),
        kind=raw.get("kind", "holiday"),
    )


def load_repository(path: str | Path) -> InMemoryRepository:
    payload = json.loads(Path(path).read_text())
    return InMemoryRepository.from_records(
        products=[_parse_product(raw) for raw in payload.get("products", [])],
        sales_history=[
            _parse_sales_observation(raw)
            for raw in payload.get("sales_history", [])
        ],
        inventory=[
            _parse_inventory_position(raw)
            for raw in payload.get("inventory", [])
        ],
        overrides=[
            _parse_override(raw)
            for raw in payload.get("overrides", [])
        ],
    )
