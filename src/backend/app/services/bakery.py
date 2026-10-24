from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app import models, schemas
from app.db import commit, utc_now
from app.services import inventory, recommendations
from app.services.common import add_event

ZERO = Decimal("0")
DEFAULT_SHARES = {"morning": 0.5, "midday": 0.3, "afternoon": 0.2}
SHARE_ORDER = ["morning", "midday", "afternoon", "evening"]


def _profile(db, product_id: int) -> models.BreadProfile | None:
    return db.scalar(
        select(models.BreadProfile).where(models.BreadProfile.product_id == product_id)
    )


def build_bake_plan(db, plan_date: date, settings, product_id: int | None = None):
    rows = list(
        db.scalars(
            select(models.Product).where(
                models.Product.active.is_(True), models.Product.domain == "bakery"
            )
        )
    )
    if product_id is not None:
        rows = [row for row in rows if row.id == product_id]
    plans = []
    for product in rows:
        profile = _profile(db, product.id)
        try:
            rec = recommendations.recommend(db, product.id, plan_date, settings)
        except KeyError:
            continue
        total = ZERO
        if rec.action == "BAKE":
            total = Decimal(rec.quantity)
        max_daily = profile.max_daily_quantity if profile else Decimal("200")
        total = min(total, max_daily)
        shares = dict(profile.daypart_shares if profile else DEFAULT_SHARES)
        shares = {key: float(value) for key, value in shares.items() if float(value) > 0}
        if not shares:
            shares = DEFAULT_SHARES
        share_total = sum(shares.values())
        slots = []
        allocated = ZERO
        keys = [key for key in SHARE_ORDER if key in shares] + [
            key for key in shares if key not in SHARE_ORDER
        ]
        for index, key in enumerate(keys):
            if index == len(keys) - 1:
                quantity = total - allocated
            else:
                quantity = (total * Decimal(str(shares[key] / share_total))).quantize(
                    Decimal("0.001")
                )
                allocated += quantity
            slots.append(
                {
                    "daypart": key,
                    "quantity": max(ZERO, quantity),
                    "status": "DRAFT",
                }
            )
        plans.append(
            {
                "plan_date": plan_date,
                "product_id": product.id,
                "sku": product.sku,
                "product_name": product.name,
                "total_quantity": total,
                "max_daily_quantity": max_daily,
                "slots": slots,
                "reason": (
                    f"{rec.action.title()} recommendation for "
                    f"{rec.forecast_horizon_days} days; capped at {max_daily}."
                ),
                "approval_required": True,
            }
        )
    return plans


def save_bake_plan(db, plan_date: date, settings, body: schemas.BakePlanOutput, actor):
    if plan_date < settings.business_today():
        raise HTTPException(status_code=409, detail="Cannot create a bake plan in the past")
    for slot in body.slots:
        existing = db.scalar(
            select(models.ProductionPlan).where(
                models.ProductionPlan.plan_date == plan_date,
                models.ProductionPlan.product_id == body.product_id,
                models.ProductionPlan.daypart == slot.daypart,
            )
        )
        if existing is None:
            existing = models.ProductionPlan(
                plan_date=plan_date,
                product_id=body.product_id,
                daypart=slot.daypart,
                planned_quantity=slot.quantity,
                status="DRAFT",
            )
            db.add(existing)
        else:
            existing.planned_quantity = slot.quantity
            existing.status = "DRAFT"
    add_event(
        db,
        "BAKE_PLAN_DRAFTED",
        "product",
        body.product_id,
        actor,
        {"plan_date": plan_date.isoformat(), "total": str(body.total_quantity)},
    )
    commit(db)
    body.slots = [
        schemas.BakePlanSlot(
            daypart=slot.daypart, quantity=slot.quantity, status="DRAFT"
        )
        for slot in body.slots
    ]
    return body


def approve_bake_plan(db, plan_date: date, product_id: int, actor):
    rows = list(
        db.scalars(
            select(models.ProductionPlan).where(
                models.ProductionPlan.plan_date == plan_date,
                models.ProductionPlan.product_id == product_id,
                models.ProductionPlan.status == "DRAFT",
            )
        )
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No draft bake plan found")
    for row in rows:
        row.status = "APPROVED"
        row.approved_by = actor.actor_name
        row.approved_at = utc_now()
    add_event(
        db,
        "BAKE_PLAN_APPROVED",
        "product",
        product_id,
        actor,
        {"plan_date": plan_date.isoformat(), "slots": len(rows)},
    )
    commit(db)
    return rows


def seasonal_advice(db, on_date: date) -> list[schemas.SeasonalAdvice]:
    month = on_date.month
    rows = db.scalars(select(models.SeasonalIngredient).order_by(models.SeasonalIngredient.name))
    advice = []
    for row in rows:
        if month not in (row.months_available or []):
            continue
        label = "local" if row.local else "available"
        advice.append(
            schemas.SeasonalAdvice(
                name=row.name,
                availability_score=float(row.availability_score),
                price_index=float(row.price_index),
                local=row.local,
                suggestion=(
                    f"{row.name} is {label} this month; "
                    f"availability {float(row.availability_score):.0%}, "
                    f"price index {float(row.price_index):.2f}."
                ),
            )
        )
    return advice


def safe_carryover(db, product_id: int, as_of: date) -> Decimal:
    return inventory.saleable_on_hand(db, product_id, as_of)
