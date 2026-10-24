from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app import models
from app.config import Settings
from app.services.timeutil import business_date, utc_start

ZERO = Decimal("0")
DECISION_EVENTS = (
    "RECOMMENDATION_APPROVED",
    "RECOMMENDATION_EDITED",
    "RECOMMENDATION_REJECTED",
)


def impact_summary(
    db,
    days: int = 30,
    as_of: date | None = None,
    settings: Settings | None = None,
) -> dict:
    settings = settings or Settings()
    selected = as_of or settings.business_today()
    start = utc_start(selected - timedelta(days=days - 1), settings)
    rows = db.execute(
        select(
            models.Product.id,
            models.Product.sku,
            models.Product.name,
            models.Product.category,
            models.Product.unit,
            models.StockMovement.movement_type,
            func.sum(models.StockMovement.quantity_delta),
        )
        .join(models.Product)
        .where(
            models.StockMovement.movement_type.in_(["WASTE", "DONATION"]),
            models.StockMovement.occurred_at >= start,
        )
        .group_by(
            models.Product.id,
            models.Product.sku,
            models.Product.name,
            models.Product.category,
            models.Product.unit,
            models.StockMovement.movement_type,
        )
    ).all()
    factors = {
        row.category: row for row in db.scalars(select(models.SDGFactor))
    }
    by_product: dict[int, dict] = {}
    for product_id, sku, name, category, unit, movement, quantity in rows:
        item = by_product.setdefault(
            product_id,
            {
                "product_id": product_id,
                "sku": sku,
                "name": name,
                "category": category,
                "unit": unit,
                "waste": ZERO,
                "donation": ZERO,
            },
        )
        item[movement.lower()] += abs(quantity)
    waste_units = sum((item["waste"] for item in by_product.values()), ZERO)
    donation_units = sum((item["donation"] for item in by_product.values()), ZERO)
    estimated_waste_kg = waste_units
    estimated_donation_kg = donation_units
    meals = ZERO
    co2e = ZERO
    for item in by_product.values():
        factor = factors.get(item["category"])
        if factor is not None:
            meals += item["donation"] * factor.meals_per_kg_donated
            co2e += item["waste"] * factor.kg_co2e_per_kg_waste
    return {
        "as_of": selected.isoformat(),
        "window_days": days,
        "assumption": (
            "Estimated impact: 1 stock unit is treated as 1 kg unless the team adds measured "
            "unit conversions. CO2e and meal figures use the configured SDG factors, which "
            "are illustrative placeholders rather than certified measurements."
        ),
        "waste_units": waste_units,
        "donation_units": donation_units,
        "estimated_waste_kg": estimated_waste_kg,
        "estimated_donation_kg": estimated_donation_kg,
        "estimated_meals": meals,
        "estimated_co2e_kg": co2e,
        "factors": [
            {
                "category": factor.category,
                "kg_co2e_per_kg_waste": str(factor.kg_co2e_per_kg_waste),
                "meals_per_kg_donated": str(factor.meals_per_kg_donated),
                "source_note": factor.source_note,
            }
            for factor in sorted(factors.values(), key=lambda row: row.category)
        ],
        "products": [
            {key: (str(value) if isinstance(value, Decimal) else value) for key, value in item.items()}
            for item in sorted(by_product.values(), key=lambda row: row["sku"])
        ],
    }


def activity_calendar(
    db, as_of: date, days: int = 120, settings: Settings | None = None
) -> dict:
    """One bucket per business day, for the contribution-style calendar."""
    settings = settings or Settings()
    days = max(7, min(days, 400))
    start = as_of - timedelta(days=days - 1)
    buckets: dict[date, dict] = {
        start + timedelta(days=offset): {
            "date": start + timedelta(days=offset),
            "sales": 0.0,
            "waste": 0.0,
            "donations": 0.0,
            "stockouts": 0,
            "decisions": 0,
        }
        for offset in range(days)
    }

    movements = db.scalars(
        select(models.StockMovement).where(
            models.StockMovement.occurred_at >= utc_start(start, settings)
        )
    ).all()
    for movement in movements:
        bucket = buckets.get(business_date(movement.occurred_at, settings))
        if bucket is None:
            continue
        quantity = abs(float(movement.quantity_delta))
        if movement.movement_type == "SALE":
            bucket["sales"] += quantity
        elif movement.movement_type == "WASTE":
            bucket["waste"] += quantity
        elif movement.movement_type == "DONATION":
            bucket["donations"] += quantity

    for event in db.scalars(
        select(models.StockoutEvent).where(models.StockoutEvent.business_date >= start)
    ).all():
        bucket = buckets.get(event.business_date)
        if bucket is not None:
            bucket["stockouts"] += 1

    for event in db.scalars(
        select(models.ActivityEvent).where(
            models.ActivityEvent.created_at >= utc_start(start, settings)
        )
    ).all():
        bucket = buckets.get(business_date(event.created_at, settings))
        if bucket is not None:
            bucket["decisions"] += 1

    def score(bucket: dict) -> float:
        return bucket["sales"] + bucket["donations"] + bucket["decisions"] * 5

    peak = max((score(bucket) for bucket in buckets.values()), default=0.0) or 1.0
    for bucket in buckets.values():
        bucket["intensity"] = round(min(1.0, score(bucket) / peak), 3)
        bucket["has_waste"] = bucket["waste"] > 0
        bucket["has_stockout"] = bucket["stockouts"] > 0

    return {
        "start_date": start.isoformat(),
        "end_date": as_of.isoformat(),
        "days": days,
        "peak_score": round(peak, 2),
        "days_detail": [
            {**bucket, "date": bucket["date"].isoformat()} for bucket in buckets.values()
        ],
    }
