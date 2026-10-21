from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app import models
from app.db import commit
from app.services import allocation, inventory
from app.services.common import add_event


class InsufficientStock(Exception):
    def __init__(self, available: Decimal):
        self.available = available


class ConcurrentStockChange(Exception):
    pass


def _canonical(body) -> dict:
    return json.loads(body.model_dump_json())


def _hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _existing(db, request_id: str, expected_hash: str):
    request = db.scalar(
        select(models.StockActionRequest).where(
            models.StockActionRequest.request_id == request_id
        )
    )
    if request is None:
        return None
    if request.canonical_hash != expected_hash:
        raise HTTPException(status_code=409, detail="request_id was used for different data")
    result = dict(request.result)
    result["replayed"] = True
    return result


def _allocation(item: allocation.Allocation) -> dict:
    return {
        "batch_id": item.batch_id,
        "batch_code": item.batch_code,
        "expiry_date": item.expiry_date.isoformat(),
        "quantity": str(item.quantity.quantize(Decimal("0.001"))),
        "unit_cost": str(item.unit_cost),
    }


def _candidates(db, product_id: int, movement_type: str, as_of):
    if movement_type in {"SALE", "DONATION"}:
        rows = inventory.saleable_batches(db, product_id, as_of)
    else:
        rows = db.scalars(
            select(models.Batch)
            .where(
                models.Batch.product_id == product_id,
                models.Batch.status.in_(["ACTIVE", "QUARANTINED"]),
                models.Batch.quantity_remaining > 0,
            )
            .order_by(
                models.Batch.expiry_date,
                models.Batch.received_date,
                models.Batch.id,
            )
        )
    return tuple(
        allocation.AllocationBatch(
            id=batch.id,
            batch_code=batch.batch_code,
            expiry_date=batch.expiry_date,
            received_date=batch.received_date,
            quantity_remaining=batch.quantity_remaining,
            unit_cost=batch.unit_cost,
            status=batch.status,
        )
        for batch in rows
    )


def _deduct(db, batch: models.Batch, quantity: Decimal) -> None:
    result = db.execute(
        update(models.Batch)
        .where(
            models.Batch.id == batch.id,
            models.Batch.quantity_remaining >= quantity,
        )
        .values(quantity_remaining=models.Batch.quantity_remaining - quantity)
    )
    if result.rowcount != 1:
        raise ConcurrentStockChange("Stock changed while allocating; retry the request")
    remaining = batch.quantity_remaining - quantity
    if remaining == 0:
        db.execute(
            update(models.Batch)
            .where(models.Batch.id == batch.id)
            .values(status="CLOSED")
        )


def _record_stockout(db, product_id: int, as_of, body, available: Decimal) -> None:
    db.add(
        models.StockoutEvent(
            product_id=product_id,
            business_date=as_of,
            daypart=body.daypart,
            requested_quantity=body.quantity,
            available_quantity=available,
            source="SALE_REJECTED",
            note=body.reason,
        )
    )
    db.commit()


def apply_stock_action(db, action, as_of):
    """Allocate stock FEFO and append one immutable movement per batch."""
    payload = _canonical(action)
    request_hash = _hash(payload)
    replay = _existing(db, action.request_id, request_hash)
    if replay is not None:
        return replay

    product = db.get(models.Product, action.product_id)
    if product is None or not product.active:
        raise HTTPException(status_code=404, detail="Active product not found")

    candidates = _candidates(db, action.product_id, action.movement_type, as_of)
    available = allocation.available_quantity(candidates)
    if available < action.quantity:
        _record_stockout(db, action.product_id, as_of, action, available)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Insufficient saleable stock: requested {action.quantity}, "
                f"available {available}"
            ),
        )

    request = models.StockActionRequest(
        request_id=action.request_id,
        request_type="STOCK_ACTION",
        product_id=action.product_id,
        canonical_hash=request_hash,
        payload=payload,
        result={},
        status="APPLIED",
    )
    db.add(request)
    try:
        db.flush()
        allocations = []
        plan = allocation.plan_allocation(candidates, action.quantity)
        for item in plan.allocations:
            batch = db.get(models.Batch, item.batch_id)
            _deduct(db, batch, item.quantity)
            db.add(
                models.StockMovement(
                    product_id=action.product_id,
                    batch_id=batch.id,
                    movement_type=action.movement_type,
                    quantity_delta=-item.quantity,
                    daypart=action.daypart,
                    reason=action.reason,
                    actor_name=action.actor_name,
                    request_id=None,
                    stock_action_id=request.id,
                )
            )
            allocations.append(_allocation(item))

        result = {
            "request_id": action.request_id,
            "product_id": action.product_id,
            "movement_type": action.movement_type,
            "requested_quantity": str(action.quantity),
            "allocated_quantity": str(plan.allocated_quantity),
            "business_date": as_of.isoformat(),
            "status": "APPLIED",
            "allocations": allocations,
            "replayed": False,
        }
        request.result = result
        add_event(
            db,
            f"STOCK_{action.movement_type}",
            "product",
            action.product_id,
            action,
            {"allocations": allocations, "request_id": action.request_id},
        )
        commit(db)
        return result
    except (ConcurrentStockChange, IntegrityError) as exc:
        db.rollback()
        replay = _existing(db, action.request_id, request_hash)
        if replay is not None:
            return replay
        if isinstance(exc, ConcurrentStockChange):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(
            status_code=409,
            detail="Stock request conflicted with another database change",
        ) from exc


def apply_adjustment(db, body, as_of):
    payload = _canonical(body)
    request_hash = _hash(payload)
    replay = _existing(db, body.request_id, request_hash)
    if replay is not None:
        return replay

    batch = db.get(models.Batch, body.batch_id)
    if batch is None or batch.product_id != body.product_id:
        raise HTTPException(status_code=404, detail="Batch not found for this product")
    if batch.status == "CLOSED" or batch.quantity_remaining <= 0:
        raise HTTPException(status_code=409, detail="Closed batches cannot be adjusted")

    delta = body.quantity_delta
    if delta < 0 and batch.quantity_remaining + delta < 0:
        raise HTTPException(status_code=409, detail="Adjustment would make stock negative")

    new_remaining = batch.quantity_remaining + delta
    values = {"quantity_remaining": new_remaining}
    if delta > 0:
        values["quantity_received"] = batch.quantity_received + delta
    if new_remaining == 0:
        values["status"] = "CLOSED"
    db.execute(update(models.Batch).where(models.Batch.id == batch.id).values(**values))

    request = models.StockActionRequest(
        request_id=body.request_id,
        request_type="ADJUSTMENT",
        product_id=body.product_id,
        canonical_hash=request_hash,
        payload=payload,
        result={},
        status="APPLIED",
    )
    db.add(request)
    db.flush()
    db.add(
        models.StockMovement(
            product_id=body.product_id,
            batch_id=batch.id,
            movement_type="ADJUSTMENT",
            quantity_delta=delta,
            reason=body.reason,
            actor_name=body.actor_name,
            request_id=None,
            stock_action_id=request.id,
        )
    )
    result = {
        "request_id": body.request_id,
        "product_id": body.product_id,
        "movement_type": "ADJUSTMENT",
        "requested_quantity": str(abs(delta).quantize(Decimal("0.001"))),
        "allocated_quantity": str(abs(delta).quantize(Decimal("0.001"))),
        "business_date": as_of.isoformat(),
        "status": "APPLIED",
        "allocations": [
            {
                "batch_id": batch.id,
                "batch_code": batch.batch_code,
                "expiry_date": batch.expiry_date.isoformat(),
                "quantity": str(abs(delta).quantize(Decimal("0.001"))),
                "unit_cost": str(batch.unit_cost),
            }
        ],
        "replayed": False,
    }
    request.result = result
    add_event(
        db,
        "STOCK_ADJUSTMENT",
        "batch",
        batch.id,
        body,
        {"quantity_delta": str(delta), "request_id": body.request_id},
    )
    commit(db)
    return result


def record_expiry_scan(db, as_of, payload: dict) -> models.ActivityEvent:
    event = models.ActivityEvent(
        event_type="EXPIRY_SCAN",
        entity_type="inventory",
        entity_id=0,
        actor_name="Expiry Scanner",
        reason="Scheduled expiry bucket scan",
        payload=payload,
    )
    db.add(event)
    db.commit()
    return event
