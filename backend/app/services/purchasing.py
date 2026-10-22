from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import models, schemas
from app.db import commit, utc_now
from app.services.common import add_event, require_approver
from app.services.receipts import create_batch_with_receipt


def _hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def receive_purchase_order(db, order_id: int, body: schemas.PurchaseReceiptInput):
    require_approver(body)
    payload = json.loads(body.model_dump_json())
    request_hash = _hash(payload)
    existing = db.scalar(
        select(models.StockActionRequest).where(
            models.StockActionRequest.request_id == body.request_id
        )
    )
    if existing is not None:
        if existing.canonical_hash != request_hash:
            raise HTTPException(status_code=409, detail="request_id was used for different data")
        result = dict(existing.result)
        result["replayed"] = True
        return result

    order = db.get(models.PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="PurchaseOrder not found")
    if order.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only an APPROVED order can be received")

    lines = {line.id: line for line in order.lines}
    request = models.StockActionRequest(
        request_id=body.request_id,
        request_type="PO_RECEIPT",
        purchase_order_id=order.id,
        canonical_hash=request_hash,
        payload=payload,
        result={},
        status="APPLIED",
    )
    db.add(request)
    batches = []
    try:
        db.flush()
        for item in body.lines:
            line = lines.get(item.purchase_order_line_id)
            if line is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Purchase order line {item.purchase_order_line_id} not found",
                )
            outstanding = line.quantity - line.received_quantity
            if item.quantity > outstanding:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Receipt exceeds outstanding quantity for line {line.id}: "
                        f"{outstanding}"
                    ),
                )
            batch_code = item.batch_code or (
                f"PO-{order.id}-{line.id}-{body.request_id[-8:]}"
            )
            batch = create_batch_with_receipt(
                db,
                product_id=line.product_id,
                batch_code=batch_code,
                quantity_received=item.quantity,
                received_date=item.received_date,
                expiry_date=item.expiry_date,
                baked_date=item.baked_date,
                unit_cost=item.unit_cost if item.unit_cost is not None else line.unit_cost,
                actor_name=body.actor_name,
                reason=body.reason,
                request_id=None,
                stock_action_id=request.id,
            )
            line.received_quantity += item.quantity
            batches.append(batch)

        if all(line.received_quantity >= line.quantity for line in order.lines):
            order.status = "RECEIVED"
            order.received_at = utc_now()

        result = {
            "request_id": body.request_id,
            "purchase_order_id": order.id,
            "status": order.status,
            "received_lines": len(batches),
            "batches": [
                schemas.BatchOutput.model_validate(batch).model_dump(mode="json")
                for batch in batches
            ],
            "replayed": False,
        }
        request.result = result
        add_event(
            db,
            "PO_RECEIVED",
            "purchase_order",
            order.id,
            body,
            {"request_id": body.request_id, "batches": [batch.id for batch in batches]},
        )
        commit(db)
        return result
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(
            select(models.StockActionRequest).where(
                models.StockActionRequest.request_id == body.request_id
            )
        )
        if existing is not None and existing.canonical_hash == request_hash:
            result = dict(existing.result)
            result["replayed"] = True
            return result
        raise HTTPException(
            status_code=409, detail="Receipt conflicted with existing data"
        ) from exc
