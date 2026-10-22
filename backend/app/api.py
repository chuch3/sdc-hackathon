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
from app.services import (
    analytics,
    bakery,
    inventory,
    purchasing,
    recommendations,
    stock_actions,
    weekly_planner,
)
from app.services.common import add_event, require_approver, require_stock_actor
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
    db: DB,
    request: Request,
    product_id: int | None = None,
    status: str | None = None,
    include_empty: bool = False,
    offset: int = Query(0, ge=0),
    limit: Limit = 100,
):
    query = select(models.Batch).order_by(
        models.Batch.expiry_date, models.Batch.received_date, models.Batch.id
    )
    if product_id is not None:
        query = query.where(models.Batch.product_id == product_id)
    if status is not None:
        query = query.where(models.Batch.status == status)
    if not include_empty:
        query = query.where(models.Batch.quantity_remaining > 0)
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


@router.post(
    "/stock-actions",
    response_model=schemas.StockActionOutput,
    status_code=201,
    tags=["Inventory"],
)
def create_stock_action(body: schemas.StockActionInput, db: DB, request: Request):
    require_stock_actor(body, body.movement_type)
    find(db, models.Product, body.product_id)
    return stock_actions.apply_stock_action(
        db, body, request.app.state.settings.business_today()
    )


@router.post(
    "/stock-adjustments",
    response_model=schemas.StockActionOutput,
    status_code=201,
    tags=["Inventory"],
)
def create_stock_adjustment(body: schemas.StockAdjustmentInput, db: DB, request: Request):
    require_approver(body)
    find(db, models.Product, body.product_id)
    return stock_actions.apply_adjustment(
        db, body, request.app.state.settings.business_today()
    )


@router.get(
    "/stock-actions/{request_id}",
    response_model=schemas.StockActionOutput,
    tags=["Inventory"],
)
def get_stock_action(request_id: str, db: DB):
    record = db.scalar(
        select(models.StockActionRequest).where(
            models.StockActionRequest.request_id == request_id
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Stock request not found")
    return record.result


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


@router.post(
    "/purchase-orders/{order_id}/receive",
    response_model=schemas.PurchaseReceiptOutput,
    status_code=201,
    tags=["Purchasing"],
)
def receive_purchase_order(
    order_id: int, body: schemas.PurchaseReceiptInput, db: DB
):
    return purchasing.receive_purchase_order(db, order_id, body)


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
    "/recommendations",
    response_model=schemas.RecommendationList,
    tags=["Forecast"],
)
def recommendations_list(
    db: DB,
    request: Request,
    domain: str | None = None,
    as_of: date | None = None,
):
    today = request.app.state.settings.business_today()
    if as_of is not None and as_of > today:
        raise HTTPException(status_code=422, detail="as_of cannot be in the future")
    selected = as_of or today
    items = recommendations.recommend_all(
        db, selected, request.app.state.settings, domain=domain
    )
    return {
        "as_of": selected,
        "engine": request.app.state.settings.forecast_engine,
        "recommendations": items,
    }


@router.post("/recommendations/{product_id}/decision", tags=["Forecast"])
def decide_recommendation(
    product_id: int, body: schemas.RecommendationDecisionInput, db: DB
):
    find(db, models.Product, product_id)
    add_event(
        db,
        f"RECOMMENDATION_{body.decision}",
        "product",
        product_id,
        body,
        {
            "action": body.action,
            "quantity": str(body.quantity),
            "edited_quantity": None
            if body.edited_quantity is None
            else str(body.edited_quantity),
            "note": body.note,
        },
    )
    commit(db)
    return {"product_id": product_id, "decision": body.decision}


@router.get(
    "/recommendations/{product_id}",
    response_model=schemas.Recommendation,
    tags=["Forecast"],
)
def recommendation(product_id: int, db: DB, request: Request):
    find(db, models.Product, product_id)
    try:
        return recommendations.recommend(
            db,
            product_id,
            request.app.state.settings.business_today(),
            request.app.state.settings,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/inventory/positions",
    response_model=list[schemas.InventoryPositionOutput],
    tags=["Inventory"],
)
def inventory_positions(db: DB, request: Request, as_of: date | None = None):
    today = request.app.state.settings.business_today()
    selected = as_of or today
    if selected > today:
        raise HTTPException(status_code=422, detail="as_of cannot be in the future")
    return inventory.inventory_positions(db, selected)


@router.get(
    "/expiry/buckets",
    response_model=schemas.ExpiryBucketOutput,
    tags=["Expiry"],
)
def expiry_buckets(db: DB, request: Request, as_of: date | None = None):
    today = request.app.state.settings.business_today()
    selected = as_of or today
    if selected > today:
        raise HTTPException(status_code=422, detail="as_of cannot be in the future")
    items = inventory.expiry_items(db, selected)
    totals = inventory.bucket_totals(items)
    value_at_risk = sum(
        (item["value"] for item in items if item["bucket"] in {"expired", "critical", "warning"}),
        Decimal("0"),
    )
    return {
        "as_of": selected,
        "totals": {key: str(value) for key, value in totals.items()},
        "value_at_risk": value_at_risk,
        "items": items,
    }


@router.get(
    "/expiry/alerts",
    response_model=schemas.ExpiryAlertOutput,
    tags=["Expiry"],
)
def expiry_alerts(
    db: DB,
    request: Request,
    as_of: date | None = None,
    horizon_days: int = Query(3, ge=0, le=60),
):
    today = request.app.state.settings.business_today()
    selected = as_of or today
    if selected > today:
        raise HTTPException(status_code=422, detail="as_of cannot be in the future")
    items = [
        item
        for item in inventory.expiry_items(db, selected)
        if item["days_to_expiry"] <= horizon_days
    ]
    return {"as_of": selected, "horizon_days": horizon_days, "alerts": items}


@router.post("/expiry/scan", tags=["Expiry"])
def expiry_scan(db: DB, request: Request):
    today = request.app.state.settings.business_today()
    items = inventory.expiry_items(db, today)
    totals = inventory.bucket_totals(items)
    payload = {
        "as_of": today.isoformat(),
        "bucket_quantities": {key: str(value) for key, value in totals.items()},
        "value_at_risk": str(
            sum(
                (
                    item["value"]
                    for item in items
                    if item["bucket"] in {"expired", "critical", "warning"}
                ),
                Decimal("0"),
            )
        ),
        "batches": len(items),
    }
    event = stock_actions.record_expiry_scan(db, today, payload)
    return {"event_id": event.id, **payload}


@router.get("/integrations/orbyte", tags=["Integrations"])
def orbyte_status(request: Request):
    settings = request.app.state.settings
    return {
        "configured": bool(settings.orbyte_base_url),
        "mode": "embed / identity / approval" if settings.orbyte_base_url else "not configured",
        "note": (
            "Orbyte is an HR/leave portal. Inventory data stays in this API; "
            "Orbyte can pass actor context or host the dashboard."
        ),
    }


@router.get("/bakery/profiles", tags=["Bakery"])
def bakery_profiles(db: DB):
    rows = db.scalars(select(models.BreadProfile).order_by(models.BreadProfile.product_id)).all()
    return [
        {
            "product_id": row.product_id,
            "weekday_factors": row.weekday_factors,
            "daypart_shares": row.daypart_shares,
            "max_daily_quantity": row.max_daily_quantity,
        }
        for row in rows
    ]


@router.put(
    "/bakery/profiles/{product_id}",
    response_model=schemas.BreadProfileOutput,
    tags=["Bakery"],
)
def upsert_bakery_profile(
    product_id: int, body: schemas.BreadProfileInput, db: DB
):
    product = find(db, models.Product, product_id)
    if product.domain != "bakery":
        raise HTTPException(status_code=409, detail="Only bakery products have bread profiles")
    profile = db.scalar(
        select(models.BreadProfile).where(models.BreadProfile.product_id == product_id)
    )
    if profile is None:
        profile = models.BreadProfile(product_id=product_id)
        db.add(profile)
    profile.weekday_factors = body.weekday_factors
    profile.daypart_shares = body.daypart_shares
    profile.max_daily_quantity = body.max_daily_quantity
    commit(db)
    return profile


@router.get(
    "/bakery/bake-plan",
    response_model=list[schemas.BakePlanOutput],
    tags=["Bakery"],
)
def get_bake_plan(
    db: DB, request: Request, plan_date: date | None = None, product_id: int | None = None
):
    selected = plan_date or request.app.state.settings.business_today()
    return bakery.build_bake_plan(
        db, selected, request.app.state.settings, product_id=product_id
    )


@router.post(
    "/bakery/bake-plan",
    response_model=schemas.BakePlanOutput,
    status_code=201,
    tags=["Bakery"],
)
def create_bake_plan(body: schemas.BakePlanRequest, db: DB, request: Request):
    plans = bakery.build_bake_plan(
        db, body.plan_date, request.app.state.settings, product_id=body.product_id
    )
    if not plans:
        raise HTTPException(status_code=404, detail="Bakery product not found")
    return bakery.save_bake_plan(
        db,
        body.plan_date,
        request.app.state.settings,
        schemas.BakePlanOutput.model_validate(plans[0]),
        body,
    )


@router.post("/bakery/bake-plan/{product_id}/approve", tags=["Bakery"])
def approve_bake_plan(
    product_id: int,
    body: schemas.Actor,
    db: DB,
    request: Request,
    plan_date: date | None = None,
):
    require_approver(body)
    selected = plan_date or request.app.state.settings.business_today()
    rows = bakery.approve_bake_plan(db, selected, product_id, body)
    return {
        "plan_date": selected,
        "product_id": product_id,
        "status": "APPROVED",
        "slots": len(rows),
    }


@router.get(
    "/bakery/seasonal-advice",
    response_model=list[schemas.SeasonalAdvice],
    tags=["Bakery"],
)
def seasonal_advice(db: DB, request: Request, on_date: date | None = None):
    selected = on_date or request.app.state.settings.business_today()
    return bakery.seasonal_advice(db, selected)


@router.get(
    "/planner/week", response_model=schemas.PlannerWeek, tags=["Planner"]
)
def planner_week(db: DB, request: Request, start: date | None = None, days: int = 7):
    """Read-only seven-day projection of stock, orders, and actions."""
    settings = request.app.state.settings
    try:
        return weekly_planner.build_week(
            db,
            as_of=settings.business_today(),
            start=start,
            days=days,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/holidays", response_model=list[schemas.HolidayOutput], tags=["Bakery"])
def list_holidays(db: DB):
    return db.scalars(select(models.HolidayCalendar).order_by(models.HolidayCalendar.holiday_date)).all()

@router.post(
    "/holidays", response_model=schemas.HolidayOutput, status_code=201, tags=["Bakery"]
)
def create_holiday(body: schemas.HolidayInput, db: DB):
    row = models.HolidayCalendar(**body.model_dump())
    db.add(row)
    commit(db)
    return row


@router.get("/analytics/impact", tags=["Impact"])
def impact(db: DB, days: int = Query(30, ge=1, le=365)):
    return analytics.impact_summary(db, days)


@router.get("/analytics/activity-calendar", tags=["Impact"])
def activity_calendar(db: DB, request: Request, days: int = Query(120, ge=7, le=400)):
    """Daily activity buckets for the contribution-style calendar."""
    settings = request.app.state.settings
    return analytics.activity_calendar(db, settings.business_today(), days, settings)


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
