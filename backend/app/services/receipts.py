from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.db import commit
from app.services.common import add_event, require_approver


def receive_batch(db, body):
    """Atomic, idempotent opening receipt. M2 can extend this service later."""
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
    batch = models.Batch(**fields, quantity_remaining=body.quantity_received)
    db.add(batch)
    try:
        db.flush()
    except Exception:
        db.rollback()
        raise
    db.add(
        models.StockMovement(
            product_id=batch.product_id,
            batch_id=batch.id,
            movement_type="RECEIPT",
            quantity_delta=batch.quantity_received,
            reason=body.reason,
            actor_name=body.actor_name,
            request_id=body.request_id,
        )
    )
    add_event(db, "BATCH_RECEIVED", "batch", batch.id, body)
    commit(db)
    db.refresh(batch)
    return batch
