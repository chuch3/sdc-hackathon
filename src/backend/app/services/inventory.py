from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

ZERO = Decimal("0")
DEFAULT_THRESHOLDS = {"bakery": 1, "dairy": 3, "produce": 2, "meat": 1, "default": 2}
BUCKET_WEIGHTS = {"expired": 1.0, "critical": 0.75, "warning": 0.4, "healthy": 0.0}


def expiry_thresholds(db: Session) -> dict[str, int]:
    setting = db.get(models.Setting, "expiry_threshold_days")
    raw = setting.value if setting and isinstance(setting.value, dict) else {}
    thresholds = dict(DEFAULT_THRESHOLDS)
    for key, value in raw.items():
        try:
            thresholds[str(key).lower()] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return thresholds


def threshold_for(db: Session, category: str, thresholds: dict[str, int] | None = None) -> int:
    values = thresholds or expiry_thresholds(db)
    return values.get(category.lower(), values.get("default", 2))


def bucket_for(days_to_expiry: int, threshold: int) -> str:
    if days_to_expiry < 0:
        return "expired"
    if days_to_expiry <= threshold:
        return "critical"
    if days_to_expiry <= threshold * 2:
        return "warning"
    return "healthy"


def days_to_expiry(batch: models.Batch, as_of: date) -> int:
    return (batch.expiry_date - as_of).days


def saleable_batches(db: Session, product_id: int, as_of: date) -> list[models.Batch]:
    return list(
        db.scalars(
            select(models.Batch)
            .where(
                models.Batch.product_id == product_id,
                models.Batch.status == "ACTIVE",
                models.Batch.expiry_date >= as_of,
                models.Batch.quantity_remaining > 0,
            )
            .order_by(
                models.Batch.expiry_date,
                models.Batch.received_date,
                models.Batch.id,
            )
        )
    )


def saleable_on_hand(db: Session, product_id: int, as_of: date) -> Decimal:
    return sum(
        (batch.quantity_remaining for batch in saleable_batches(db, product_id, as_of)),
        ZERO,
    )


def remaining_shelf_life_days(db: Session, product_id: int, as_of: date) -> int:
    batches = saleable_batches(db, product_id, as_of)
    if not batches:
        return 99
    return max(0, min(days_to_expiry(batch, as_of) for batch in batches))


def on_order_totals(
    db: Session, product_id: int, as_of: date
) -> tuple[Decimal, Decimal]:
    rows = db.execute(
        select(models.PurchaseOrderLine, models.PurchaseOrder.expected_date)
        .join(models.PurchaseOrder)
        .where(
            models.PurchaseOrderLine.product_id == product_id,
            models.PurchaseOrder.status == "APPROVED",
        )
    ).all()
    available, overdue = ZERO, ZERO
    for line, expected in rows:
        outstanding = line.quantity - line.received_quantity
        if outstanding <= 0:
            continue
        if expected < as_of:
            overdue += outstanding
        else:
            available += outstanding
    return available, overdue


def allowed_actions(batch: models.Batch, as_of: date) -> list[str]:
    expired = batch.expiry_date < as_of
    if batch.quantity_remaining <= 0:
        return []
    if batch.status == "QUARANTINED":
        return ["WASTE"]
    if expired:
        return ["WASTE"]
    if batch.status != "ACTIVE":
        return []
    return ["SALE", "DONATION", "WASTE"]


def expiry_items(db: Session, as_of: date) -> list[dict]:
    thresholds = expiry_thresholds(db)
    product_ids = set(
        db.scalars(select(models.Batch.product_id).where(models.Batch.quantity_remaining > 0))
    )
    items: list[dict] = []
    for product_id in product_ids:
        product = db.get(models.Product, product_id)
        if product is None:
            continue
        products_threshold = threshold_for(db, product.category, thresholds)
        batches = db.scalars(
            select(models.Batch)
            .where(
                models.Batch.product_id == product_id,
                models.Batch.quantity_remaining > 0,
            )
            .order_by(models.Batch.expiry_date, models.Batch.received_date, models.Batch.id)
        )
        for batch in batches:
            days = days_to_expiry(batch, as_of)
            value = batch.quantity_remaining * batch.unit_cost
            items.append(
                {
                    "bucket": bucket_for(days, products_threshold),
                    "product_id": product.id,
                    "sku": product.sku,
                    "name": product.name,
                    "batch_id": batch.id,
                    "batch_code": batch.batch_code,
                    "quantity": batch.quantity_remaining,
                    "unit_cost": batch.unit_cost,
                    "value": value,
                    "expiry_date": batch.expiry_date,
                    "days_to_expiry": days,
                    "remaining_shelf_life_days": max(0, days),
                    "allowed_actions": allowed_actions(batch, as_of),
                }
            )
    items.sort(key=lambda item: (item["expiry_date"], item["batch_id"]))
    return items


def bucket_totals(items: list[dict]) -> dict[str, Decimal]:
    totals = {name: ZERO for name in BUCKET_WEIGHTS}
    for item in items:
        totals[item["bucket"]] += item["quantity"]
    return totals


def risk_score(items: list[dict]) -> float:
    total_value = sum((item["value"] for item in items), ZERO)
    if total_value <= 0:
        return 0.0
    at_risk = sum(
        (item["value"] * Decimal(str(BUCKET_WEIGHTS[item["bucket"]])) for item in items),
        ZERO,
    )
    return round(float(at_risk / total_value), 4)


def inventory_positions(db: Session, as_of: date) -> list[dict]:
    products = list(
        db.scalars(select(models.Product).where(models.Product.active.is_(True)).order_by(models.Product.id))
    )
    items_by_product: dict[int, list[dict]] = {}
    for item in expiry_items(db, as_of):
        items_by_product.setdefault(item["product_id"], []).append(item)
    result = []
    for product in products:
        items = items_by_product.get(product.id, [])
        physical = sum((item["quantity"] for item in items), ZERO)
        saleable = sum(
            (item["quantity"] for item in items if item["bucket"] != "expired" and "SALE" in item["allowed_actions"]),
            ZERO,
        )
        expired = sum((item["quantity"] for item in items if item["bucket"] == "expired"), ZERO)
        quarantined = sum(
            (
                item["quantity"]
                for item in items
                if "SALE" not in item["allowed_actions"] and item["bucket"] != "expired"
            ),
            ZERO,
        )
        on_order, overdue = on_order_totals(db, product.id, as_of)
        earliest = min((item["expiry_date"] for item in items), default=None)
        remaining = (
            max(0, (earliest - as_of).days) if earliest is not None else 99
        )
        result.append(
            {
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "category": product.category,
                "unit": product.unit,
                "physical_on_hand": physical,
                "saleable_on_hand": saleable,
                "expired_quantity": expired,
                "quarantined_quantity": quarantined,
                "on_order": on_order,
                "overdue_on_order": overdue,
                "earliest_expiry": earliest,
                "remaining_shelf_life_days": remaining,
                "risk_score": risk_score(items),
                "buckets": bucket_totals(items),
            }
        )
    return result


def empty_position(product: models.Product) -> dict:
    return {
        "product_id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "unit": product.unit,
        "physical_on_hand": ZERO,
        "saleable_on_hand": ZERO,
        "expired_quantity": ZERO,
        "quarantined_quantity": ZERO,
        "on_order": ZERO,
        "overdue_on_order": ZERO,
        "earliest_expiry": None,
        "remaining_shelf_life_days": 99,
        "risk_score": 0.0,
        "buckets": {name: ZERO for name in BUCKET_WEIGHTS},
    }
