from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.db import commit
from app.services.common import add_event, require_approver


def create_batch_with_receipt(
    db,
    *,
    product_id: int,
    batch_code: str,
    quantity_received,
    received_date,
    expiry_date,
    baked_date=None,
    unit_cost=None,
    actor_name: str,
    reason: str,
    request_id: str | None = None,
    stock_action_id: int | None = None,
    commit_now: bool = False,
):
    batch = models.Batch(
        product_id=product_id,
        batch_code=batch_code,
        quantity_received=quantity_received,
        quantity_remaining=quantity_received,
        received_date=received_date,
        baked_date=baked_date,
        expiry_date=expiry_date,
        unit_cost=unit_cost if unit_cost is not None else 0,
    )
    db.add(batch)
    db.flush()
    db.add(
        models.StockMovement(
            product_id=batch.product_id,
            batch_id=batch.id,
            movement_type="RECEIPT",
            quantity_delta=batch.quantity_received,
            reason=reason,
            actor_name=actor_name,
            request_id=request_id,
            stock_action_id=stock_action_id,
        )
    )
    if commit_now:
        commit(db)
        db.refresh(batch)
    return batch


def receive_batch(db, body):
    """Atomic, idempotent opening receipt. M2 extends this service."""
    require_approver(body)
    product = db.get(models.Product, body.product_id)
    if not product or not product.active:
        raise HTTPException(status_code=404, detail="Active product not found")
    fields = body.model_dump(exclude={"actor_name", "actor_role", "reason", "request_id"})
    previous = db.scalar(
        select(models.StockMovement).where(models.StockMovement.request_id == body.request_id)
    )
    if previous:
        batch = db.get(models.Batch, previous.batch_id)
        if previous.movement_type != "RECEIPT" or any(
            getattr(batch, key) != value for key, value in fields.items()
        ):
            raise HTTPException(status_code=409, detail="request_id was used for different data")
        return batch
    try:
        batch = create_batch_with_receipt(
            db,
            product_id=body.product_id,
            batch_code=body.batch_code,
            quantity_received=body.quantity_received,
            received_date=body.received_date,
            expiry_date=body.expiry_date,
            baked_date=body.baked_date,
            unit_cost=body.unit_cost,
            actor_name=body.actor_name,
            reason=body.reason,
            request_id=body.request_id,
        )
    except Exception:
        db.rollback()
        raise
    add_event(db, "BATCH_RECEIVED", "batch", batch.id, body)
    commit(db)
    db.refresh(batch)
    return batch
