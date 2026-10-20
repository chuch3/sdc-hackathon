import csv
import io
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import commit, get_db, utc_now
from app.services import recommendations, stock_actions
from app.services.common import add_event, require_approver
from app.services.receipts import receive_batch

router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=2000)]


def find(db, model, record_id):
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return record


def check_supplier(db, supplier_id):
    if supplier_id is not None:
        supplier = find(db, models.Supplier, supplier_id)
        if not supplier.active:
            raise HTTPException(status_code=409, detail="Supplier is archived")


@router.get("/suppliers", response_model=list[schemas.SupplierOutput], tags=["Suppliers"])
def list_suppliers(db: DB, include_archived: bool = False):
    query = select(models.Supplier).order_by(models.Supplier.id)
    if not include_archived:
        query = query.where(models.Supplier.active.is_(True))
    return db.scalars(query).all()


@router.post(
    "/suppliers", response_model=schemas.SupplierOutput, status_code=201, tags=["Suppliers"]
)
def create_supplier(body: schemas.SupplierInput, db: DB):
    record = models.Supplier(**body.model_dump())
    db.add(record)
    commit(db)
    return record


@router.get("/suppliers/{supplier_id}", response_model=schemas.SupplierOutput, tags=["Suppliers"])
def get_supplier(supplier_id: int, db: DB):
    return find(db, models.Supplier, supplier_id)


@router.put("/suppliers/{supplier_id}", response_model=schemas.SupplierOutput, tags=["Suppliers"])
def update_supplier(supplier_id: int, body: schemas.SupplierInput, db: DB):
    record = find(db, models.Supplier, supplier_id)
    for key, value in body.model_dump().items():
        setattr(record, key, value)
    commit(db)
    return record


@router.delete("/suppliers/{supplier_id}", status_code=204, tags=["Suppliers"])
def archive_supplier(supplier_id: int, db: DB):
    find(db, models.Supplier, supplier_id).active = False
    commit(db)
    return Response(status_code=204)


@router.get("/products", response_model=list[schemas.ProductOutput], tags=["Products"])
def list_products(
    db: DB, include_archived: bool = False, offset: int = Query(0, ge=0), limit: Limit = 100
):
    query = select(models.Product).order_by(models.Product.id).offset(offset).limit(limit)
    if not include_archived:
        query = query.where(models.Product.active.is_(True))
    return db.scalars(query).all()


@router.post("/products", response_model=schemas.ProductOutput, status_code=201, tags=["Products"])
def create_product(body: schemas.ProductInput, db: DB):
    check_supplier(db, body.supplier_id)
    record = models.Product(**body.model_dump())
    db.add(record)
    commit(db)
    return record


@router.get("/products/{product_id}", response_model=schemas.ProductOutput, tags=["Products"])
def get_product(product_id: int, db: DB):
    return find(db, models.Product, product_id)


@router.put("/products/{product_id}", response_model=schemas.ProductOutput, tags=["Products"])
def update_product(product_id: int, body: schemas.ProductInput, db: DB):
    record = find(db, models.Product, product_id)
    if body.unit != record.unit:
        has_batches = db.scalar(
            select(models.Batch.id).where(models.Batch.product_id == product_id)
        )
        if has_batches:
            raise HTTPException(status_code=409, detail="Unit cannot change after receiving stock")
    check_supplier(db, body.supplier_id)
    for key, value in body.model_dump().items():
        setattr(record, key, value)
    commit(db)
    return record


@router.delete("/products/{product_id}", status_code=204, tags=["Products"])
def archive_product(product_id: int, db: DB):
    find(db, models.Product, product_id).active = False
    commit(db)
    return Response(status_code=204)


@router.get("/batches", response_model=list[schemas.BatchOutput], tags=["Batches"])
def list_batches(
    db: DB, product_id: int | None = None, offset: int = Query(0, ge=0), limit: Limit = 100
):
    query = select(models.Batch).order_by(
        models.Batch.expiry_date, models.Batch.received_date, models.Batch.id
    )
    if product_id is not None:
        query = query.where(models.Batch.product_id == product_id)
    return db.scalars(query.offset(offset).limit(limit)).all()


@router.get("/batches/{batch_id}", response_model=schemas.BatchOutput, tags=["Batches"])
def get_batch(batch_id: int, db: DB):
    return find(db, models.Batch, batch_id)


@router.post("/batches", response_model=schemas.BatchOutput, status_code=201, tags=["Batches"])
def create_batch(body: schemas.BatchInput, db: DB):
    return receive_batch(db, body)


@router.patch("/batches/{batch_id}/status", response_model=schemas.BatchOutput, tags=["Batches"])
def change_batch_status(batch_id: int, body: schemas.BatchStatusInput, db: DB):
    require_approver(body)
    batch = find(db, models.Batch, batch_id)
    if batch.quantity_remaining <= 0:
        raise HTTPException(status_code=409, detail="An empty batch cannot be reopened")
    previous = batch.status
    batch.status = body.status
    add_event(
        db,
        "BATCH_STATUS_CHANGED",
        "batch",
        batch_id,
        body,
        {"before": previous, "after": body.status},
    )
    commit(db)
    return batch


@router.get("/movements", response_model=list[schemas.MovementOutput], tags=["Ledger"])
def list_movements(
    db: DB, product_id: int | None = None, offset: int = Query(0, ge=0), limit: Limit = 100
):
    query = select(models.StockMovement).order_by(
        models.StockMovement.occurred_at.desc(), models.StockMovement.id.desc()
    )
    if product_id is not None:
        query = query.where(models.StockMovement.product_id == product_id)
    return db.scalars(query.offset(offset).limit(limit)).all()


@router.post("/stock-actions", tags=["M2 integration"])
def create_stock_action(body: schemas.StockActionInput, db: DB, request: Request):
    require_approver(body)
    find(db, models.Product, body.product_id)
    try:
        return stock_actions.apply_stock_action(
            db, body, request.app.state.settings.business_today()
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post(
    "/purchase-orders",
    response_model=schemas.PurchaseOrderOutput,
    status_code=201,
    tags=["Purchasing"],
)
def create_purchase_order(body: schemas.PurchaseOrderInput, db: DB):
    check_supplier(db, body.supplier_id)
    for line in body.lines:
        if not find(db, models.Product, line.product_id).active:
            raise HTTPException(status_code=409, detail="Cannot order an archived product")
    order = models.PurchaseOrder(supplier_id=body.supplier_id, expected_date=body.expected_date)
    order.lines = [models.PurchaseOrderLine(**line.model_dump()) for line in body.lines]
    db.add(order)
    commit(db)
    return order


@router.get(
    "/purchase-orders", response_model=list[schemas.PurchaseOrderOutput], tags=["Purchasing"]
)
def list_purchase_orders(db: DB):
    return db.scalars(select(models.PurchaseOrder).order_by(models.PurchaseOrder.id)).all()


@router.get(
    "/purchase-orders/{order_id}", response_model=schemas.PurchaseOrderOutput, tags=["Purchasing"]
)
def get_purchase_order(order_id: int, db: DB):
    return find(db, models.PurchaseOrder, order_id)


@router.post(
    "/purchase-orders/{order_id}/approve",
    response_model=schemas.PurchaseOrderOutput,
    tags=["Purchasing"],
)
def approve_purchase_order(order_id: int, body: schemas.Actor, db: DB):
    require_approver(body)
    order = find(db, models.PurchaseOrder, order_id)
    if order.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only a DRAFT order can be approved")
    check_supplier(db, order.supplier_id)
    for line in order.lines:
        if not find(db, models.Product, line.product_id).active:
            raise HTTPException(status_code=409, detail="An order product has been archived")
    order.status, order.approved_by, order.approved_at = "APPROVED", body.actor_name, utc_now()
    add_event(db, "PO_APPROVED", "purchase_order", order_id, body)
    commit(db)
    return order


@router.post(
    "/purchase-orders/{order_id}/cancel",
    response_model=schemas.PurchaseOrderOutput,
    tags=["Purchasing"],
)
def cancel_purchase_order(order_id: int, body: schemas.Actor, db: DB):
    require_approver(body)
    order = find(db, models.PurchaseOrder, order_id)
    if order.status not in {"DRAFT", "APPROVED"}:
        raise HTTPException(status_code=409, detail="This order cannot be cancelled")
    if any(line.received_quantity > 0 for line in order.lines):
        raise HTTPException(status_code=409, detail="Ask M2 to handle a partly received order")
    order.status = "CANCELLED"
    add_event(db, "PO_CANCELLED", "purchase_order", order_id, body)
    commit(db)
    return order


@router.get(
    "/products/{product_id}/on-order", response_model=schemas.OnOrderOutput, tags=["Purchasing"]
)
def on_order(product_id: int, db: DB, request: Request, through: date | None = None):
    find(db, models.Product, product_id)
    today = request.app.state.settings.business_today()
    if through is not None and through < today:
        raise HTTPException(status_code=422, detail="through must be today or later")
    rows = db.execute(
        select(models.PurchaseOrderLine, models.PurchaseOrder.expected_date)
        .join(models.PurchaseOrder)
        .where(
            models.PurchaseOrderLine.product_id == product_id,
            models.PurchaseOrder.status == "APPROVED",
        )
    ).all()
    quantity, overdue = Decimal("0"), Decimal("0")
    for line, expected in rows:
        outstanding = line.quantity - line.received_quantity
        if expected < today:
            overdue += outstanding
        elif through is None or expected <= through:
            quantity += outstanding
    return {
        "product_id": product_id,
        "as_of": today,
        "through": through,
        "quantity": quantity,
        "overdue_quantity": overdue,
    }


@router.get(
    "/recommendations/{product_id}", response_model=schemas.Recommendation, tags=["M3 integration"]
)
def recommendation(product_id: int, db: DB, request: Request):
    find(db, models.Product, product_id)
    try:
        return recommendations.recommend(
            db, product_id, request.app.state.settings.business_today()
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.get("/activity", tags=["Audit"])
def activity(db: DB, limit: Limit = 100):
    records = db.scalars(
        select(models.ActivityEvent).order_by(models.ActivityEvent.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "actor_name": row.actor_name,
            "reason": row.reason,
            "payload": row.payload,
            "created_at": row.created_at,
        }
        for row in records
    ]


def csv_cell(value):
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


@router.get("/exports/inventory.csv", tags=["Exports"])
def inventory_csv(db: DB, request: Request):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "batch_id",
            "sku",
            "product",
            "unit",
            "remaining",
            "expiry_date",
            "status",
            "available_today",
            "business_date",
        ]
    )
    today = request.app.state.settings.business_today()
    for batch, product in db.execute(
        select(models.Batch, models.Product).join(models.Product).order_by(models.Batch.id)
    ):
        available = (
            product.active
            and batch.status == "ACTIVE"
            and batch.expiry_date >= today
            and batch.quantity_remaining > 0
        )
        writer.writerow(
            [
                batch.id,
                csv_cell(product.sku),
                csv_cell(product.name),
                csv_cell(product.unit),
                batch.quantity_remaining,
                batch.expiry_date,
                batch.status,
                available,
                today,
            ]
        )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="inventory.csv"'},
    )
