from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app import models
from app.config import Settings
from app.services.timeutil import business_date

WINDOW_DAYS = 28
REQUIRED_DAYS = 14


def _last_import_at(db) -> datetime | None:
    candidates: list[datetime] = []
    settings_rows = db.scalars(
        select(models.Setting).where(models.Setting.key.like("import_sales:%"))
    ).all()
    for row in settings_rows:
        value = row.value if isinstance(row.value, dict) else {}
        for key in ("imported_at", "committed_at", "created_at"):
            raw = value.get(key)
            if not raw:
                continue
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            candidates.append(parsed)
    events = db.scalars(
        select(models.ActivityEvent).where(
            models.ActivityEvent.event_type.in_(["SALES_IMPORTED", "SALES_IMPORT_COMMITTED"])
        )
    ).all()
    candidates.extend(event.created_at for event in events)
    return max(candidates, default=None)


def build_readiness(db, settings: Settings, as_of: date) -> dict:
    products = db.scalars(
        select(models.Product).where(models.Product.active.is_(True))
    ).all()
    product_ids = [product.id for product in products]
    window_start = as_of - timedelta(days=WINDOW_DAYS - 1)

    product_sale_days: dict[int, set[date]] = {product_id: set() for product_id in product_ids}
    last_sale_date: date | None = None

    if product_ids:
        movements = db.execute(
            select(models.StockMovement.product_id, models.StockMovement.occurred_at)
            .where(
                models.StockMovement.product_id.in_(product_ids),
                models.StockMovement.movement_type == "SALE",
            )
            .order_by(models.StockMovement.occurred_at, models.StockMovement.id)
        ).all()
        for product_id, occurred_at in movements:
            day = business_date(occurred_at, settings)
            if last_sale_date is None or day > last_sale_date:
                last_sale_date = day
            if day >= window_start:
                product_sale_days[product_id].add(day)

    censored_by_product: dict[int, set[date]] = {
        product_id: set() for product_id in product_ids
    }
    if product_ids:
        censored = db.execute(
            select(models.StockoutEvent.product_id, models.StockoutEvent.business_date).where(
                models.StockoutEvent.product_id.in_(product_ids),
                models.StockoutEvent.business_date >= window_start,
                models.StockoutEvent.business_date <= as_of,
            )
        ).all()
        for product_id, business_day in censored:
            censored_by_product[product_id].add(business_day)
    censored_days = set().union(*censored_by_product.values()) if product_ids else set()

    usable_days: set[date] = set()
    products_ready = 0
    for product_id in product_ids:
        product_days = product_sale_days[product_id] - censored_by_product[product_id]
        usable_days |= product_days
        if len(product_days) >= REQUIRED_DAYS:
            products_ready += 1
    valid_days = len(usable_days)
    products_active = len(product_ids)

    if products_active == 0:
        stage = "no_products"
    elif valid_days == 0:
        stage = "no_sales"
    elif valid_days < REQUIRED_DAYS or products_ready == 0:
        stage = "thin_history"
    elif last_sale_date == as_of:
        stage = "live"
    else:
        stage = "ready"

    checks = [
        {
            "key": "products",
            "label": "Products",
            "ok": products_active > 0,
            "detail": (
                f"{products_active} active product(s)."
                if products_active
                else "No active products yet."
            ),
        },
        {
            "key": "sales",
            "label": "Sales history",
            "ok": valid_days > 0,
            "detail": (
                f"{valid_days} usable day(s) in the last {WINDOW_DAYS} days."
                if valid_days
                else f"No sales in the last {WINDOW_DAYS} days."
            ),
        },
        {
            "key": "coverage",
            "label": "History depth",
            "ok": valid_days >= REQUIRED_DAYS and products_ready > 0,
            "detail": (
                f"{valid_days} of {REQUIRED_DAYS} required days · "
                f"{products_ready} of {products_active} product(s) ready."
            ),
        },
        {
            "key": "stockouts",
            "label": "Stockout-censored days",
            "ok": True,
            "detail": (
                f"{len(censored_days)} day(s) excluded from training."
                if censored_days
                else "None detected in the window."
            ),
        },
    ]

    reason = (
        "Add products and opening stock before the planner can work."
        if stage == "no_products"
        else (
            f"Import at least {REQUIRED_DAYS} days of sales so forecasts can learn from this shop."
            if stage == "no_sales"
            else (
                f"Only {valid_days} of {REQUIRED_DAYS} required days are usable. "
                "Import more sales history to unlock reliable forecasts."
                if stage == "thin_history"
                else (
                    "Sales are flowing in today; recommendations update as the ledger changes."
                    if stage == "live"
                    else "Forecasts have enough history. Review today's plan."
                )
            )
        )
    )
    next_action = {
        "no_products": {"label": "Add products", "page": "Inventory"},
        "no_sales": {"label": "Import sales", "page": "Settings"},
        "thin_history": {"label": "Import more sales", "page": "Settings"},
        "ready": {"label": "Review today's plan", "page": "Today"},
        "live": {"label": "Review today's plan", "page": "Today"},
    }[stage]

    return {
        "as_of": as_of,
        "stage": stage,
        "products_active": products_active,
        "products_ready": products_ready,
        "valid_days": valid_days,
        "required_days": REQUIRED_DAYS,
        "censored_days": len(censored_days),
        "last_sale_date": last_sale_date,
        "last_import_at": _last_import_at(db),
        "checks": checks,
        "next_action": {**next_action, "reason": reason},
    }
