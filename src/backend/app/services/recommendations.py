from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app import models, schemas
from app.config import Settings
from app.services.forecast_repository import build_pipeline

CONFIDENCE = {"low": 0.35, "medium": 0.65, "high": 0.85}
DECISION_EVENTS = (
    "RECOMMENDATION_APPROVED",
    "RECOMMENDATION_EDITED",
    "RECOMMENDATION_REJECTED",
)


def _latest_decisions(db) -> dict[int, dict]:
    """The most recent decision per product, so the UI can show what was already done."""
    rows = db.scalars(
        select(models.ActivityEvent)
        .where(models.ActivityEvent.event_type.in_(DECISION_EVENTS))
        .order_by(models.ActivityEvent.id.desc())
    ).all()
    latest: dict[int, dict] = {}
    for row in rows:
        if row.entity_type != "product" or row.entity_id in latest:
            continue
        latest[row.entity_id] = {
            "decision": row.event_type.removeprefix("RECOMMENDATION_"),
            "decided_at": row.created_at,
            "decided_by": row.actor_name,
        }
    return latest


def _pipeline(db, as_of: date, settings: Settings):
    return build_pipeline(db, as_of, settings)


def _jsonable(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _to_schema(product_id: int, item, engine: str, decision: dict | None = None) -> schemas.Recommendation:
    return schemas.Recommendation(
        product_id=product_id,
        sku=item.product_sku,
        product_name=item.product_name,
        action=item.action.value,
        quantity=Decimal(str(round(float(item.quantity), 3))).quantize(Decimal("0.001")),
        rationale=item.rationale,
        confidence=CONFIDENCE.get(item.confidence.value, 0.35),
        expiry_risk=item.expiry_risk,
        forecast_horizon_days=item.forecast_horizon_days,
        why=list(item.why),
        reason_codes=[code.value for code in item.reason_codes],
        calculation={key: float(value) for key, value in item.calculation.items()},
        model_name=item.forecast.model_name,
        model_version=item.forecast.model_version,
        forecast_run_id=item.forecast_run_id,
        input_snapshot_id=item.input_snapshot_id,
        actionable=item.forecast.actionable,
        data_quality=_jsonable(asdict(item.forecast.data_quality)),
        forecast_lower=float(item.forecast.total_lower),
        forecast_upper=float(item.forecast.total_upper),
        approval_required=item.approval_required,
        engine=engine,
        decision=decision["decision"] if decision else None,
        decided_at=decision["decided_at"] if decision else None,
        decided_by=decision["decided_by"] if decision else "",
    )


def recommend(db, product_id: int, as_of, settings: Settings | None = None):
    settings = settings or Settings()
    product = db.get(models.Product, product_id)
    if product is None or not product.active:
        raise KeyError(f"unknown or archived product: {product_id}")
    pipeline = _pipeline(db, as_of, settings)
    item = pipeline.recommend_one(product.sku, as_of)
    decision = _latest_decisions(db).get(product.id)
    return _to_schema(product.id, item, settings.forecast_engine, decision)


def recommend_all(db, as_of, settings: Settings | None = None, domain: str | None = None):
    settings = settings or Settings()
    pipeline = _pipeline(db, as_of, settings)
    rows = list(
        db.scalars(
            select(models.Product).where(models.Product.active.is_(True)).order_by(models.Product.id)
        )
    )
    if domain:
        rows = [row for row in rows if row.domain == domain]
    by_sku = {row.sku: row.id for row in rows}
    items = pipeline.recommend_all(as_of, [row.sku for row in rows])
    decisions = _latest_decisions(db)
    return [
        _to_schema(
            by_sku[item.product_sku],
            item,
            settings.forecast_engine,
            decisions.get(by_sku[item.product_sku]),
        )
        for item in items
        if item.product_sku in by_sku
    ]
