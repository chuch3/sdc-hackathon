from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.config import Settings
from app.db import commit, utc_now
from app.services.versioning import data_version

ALIASES = {
    "date": (
        "date",
        "business_date",
        "sale_date",
        "sold_at",
        "timestamp",
        "day",
    ),
    "sku": (
        "sku",
        "product_sku",
        "product",
        "item",
        "item_code",
    ),
    "quantity": (
        "quantity",
        "qty",
        "units",
        "sold",
        "quantity_sold",
    ),
    "daypart": (
        "daypart",
        "day_part",
        "part_of_day",
        "shift",
    ),
    "stockout": (
        "stockout",
        "stock_out",
        "out_of_stock",
        "censored",
        "stockout_flag",
    ),
}
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%d/%m/%y",
    "%m/%d/%y",
)
TRUTHY = {"1", "true", "t", "yes", "y", "on"}
MAX_QUANTITY = Decimal("99999999999.999")
ASSUMPTIONS = [
    "Imported rows are historical sales. They create closed batches and dated SALE "
    "movements and do not change today's saleable stock.",
    "Unknown SKUs and malformed rows are skipped and reported, so a messy export can be "
    "cleaned up without blocking the usable rows.",
    "Duplicate identical rows in one upload are imported once. Reusing a request_id "
    "returns the original result instead of importing twice.",
    "Day-first dates are preferred for ambiguous values such as 03/04/2026.",
]


def _clean_header(value: str | None) -> str:
    return (value or "").strip().lower()


def _resolve_mapping(columns: list[str], mapping) -> dict[str, str | None]:
    by_alias = {_clean_header(column): column for column in columns}
    resolved: dict[str, str | None] = {}
    for field, aliases in ALIASES.items():
        explicit = getattr(mapping, field, None)
        if explicit:
            if explicit not in columns:
                raise HTTPException(
                    status_code=422,
                    detail=f"Mapping column '{explicit}' for {field} is not in the CSV header",
                )
            resolved[field] = explicit
            continue
        resolved[field] = next(
            (by_alias[alias] for alias in aliases if alias in by_alias), None
        )
    missing = [field for field in ("date", "sku", "quantity") if not resolved[field]]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not find required CSV column(s): "
                + ", ".join(missing)
                + ". Choose a date, SKU and quantity column explicitly."
            ),
        )
    return resolved


def _parse_date(raw: str) -> date:
    value = raw.strip()
    if not value:
        raise ValueError("date is blank")
    if "T" in value:
        value = value.split("T", 1)[0]
    elif " " in value:
        value = value.split(" ", 1)[0]
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{raw.strip()}'")


def _parse_quantity(raw: str) -> Decimal:
    value = raw.strip().replace(",", "")
    if not value:
        raise ValueError("quantity is blank")
    try:
        quantity = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"'{raw.strip()}' is not a number") from exc
    if not quantity.is_finite():
        raise ValueError("quantity must be a finite number")
    if quantity < 0:
        raise ValueError("quantity cannot be negative")
    if quantity > MAX_QUANTITY:
        raise ValueError("quantity is too large")
    return quantity.quantize(Decimal("0.001"))


def _parse_daypart(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    return value[:20] or None


def _parse_stockout(raw: str | None) -> bool:
    return (raw or "").strip().lower() in TRUTHY


def _norm_sku(raw: str | None) -> str:
    return (raw or "").strip()


def _content_hash(body) -> str:
    payload = json.dumps(
        {"csv_text": body.csv_text, "mapping": body.mapping.model_dump()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _request_key(request_id: str) -> str:
    digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    return f"import_sales:{digest}"


def _batch_code(request_id: str, sku: str) -> str:
    code = f"IMPORT-HIST-{request_id}-{sku}"
    if len(code) <= 80:
        return code
    suffix = hashlib.sha256(code.encode("utf-8")).hexdigest()[:8]
    return f"IMPORT-HIST-{request_id[:20]}-{sku[:35]}-{suffix}"


def _movement_request_id(request_id: str, sku: str, index: int, kind: str) -> str:
    digest = hashlib.sha256(
        f"{request_id}:{sku}:{index}:{kind}".encode("utf-8")
    ).hexdigest()[:40]
    return f"import:{digest}"


def _parse_rows(db, body, settings: Settings) -> tuple[dict, list[dict], list[dict]]:
    if len(body.csv_text) > 5_000_000:
        raise HTTPException(status_code=413, detail="CSV upload is too large")
    reader = csv.DictReader(io.StringIO(body.csv_text))
    columns = list(reader.fieldnames or [])
    if not columns:
        raise HTTPException(status_code=422, detail="CSV has no header row")
    rows = list(reader)
    if len(rows) > settings.import_max_rows:
        raise HTTPException(
            status_code=422,
            detail=(
                f"CSV has {len(rows)} rows; the limit is {settings.import_max_rows}. "
                "Split the file into smaller uploads."
            ),
        )
    mapping = _resolve_mapping(columns, body.mapping)
    products = {
        product.sku: product
        for product in db.scalars(
            select(models.Product).where(models.Product.active.is_(True))
        )
    }
    parsed: list[dict] = []
    issues: list[dict] = []
    duplicates = 0
    seen: set[tuple] = set()
    unknown_skus: set[str] = set()

    for row_number, row in enumerate(rows, start=2):
        raw_date = row.get(mapping["date"]) or ""
        raw_sku = row.get(mapping["sku"]) or ""
        raw_quantity = row.get(mapping["quantity"]) or ""
        raw_daypart = row.get(mapping["daypart"]) if mapping["daypart"] else None
        raw_stockout = row.get(mapping["stockout"]) if mapping["stockout"] else None

        if not (raw_date.strip() or raw_sku.strip() or raw_quantity.strip()):
            continue
        try:
            day = _parse_date(raw_date)
        except ValueError as exc:
            issues.append({"row": row_number, "field": "date", "message": str(exc)})
            continue
        sku = _norm_sku(raw_sku)
        if not sku:
            issues.append({"row": row_number, "field": "sku", "message": "SKU is blank"})
            continue
        product = products.get(sku)
        if product is None:
            unknown_skus.add(sku)
            issues.append(
                {
                    "row": row_number,
                    "field": "sku",
                    "message": f"SKU '{sku}' does not match an active product",
                }
            )
            continue
        try:
            quantity = _parse_quantity(raw_quantity)
        except ValueError as exc:
            issues.append({"row": row_number, "field": "quantity", "message": str(exc)})
            continue
        if day > settings.business_today():
            issues.append(
                {
                    "row": row_number,
                    "field": "date",
                    "message": "future dates cannot be imported",
                }
            )
            continue

        daypart = _parse_daypart(raw_daypart)
        stockout = _parse_stockout(raw_stockout)
        key = (product.id, day, daypart, str(quantity), stockout)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        parsed.append(
            {
                "row": row_number,
                "product_id": product.id,
                "sku": product.sku,
                "day": day,
                "quantity": quantity,
                "daypart": daypart,
                "stockout": stockout,
            }
        )

    stats = {
        "columns": columns,
        "mapping": mapping,
        "total_rows": len(rows),
        "valid_rows": len(parsed),
        "invalid_rows": len(issues),
        "duplicate_rows": duplicates,
        "unknown_skus": sorted(unknown_skus),
        "stockout_rows": sum(1 for row in parsed if row["stockout"]),
        "date_start": min((row["day"] for row in parsed), default=None),
        "date_end": max((row["day"] for row in parsed), default=None),
        "valid_days": len(
            {row["day"] for row in parsed if row["quantity"] > 0 and not row["stockout"]}
        ),
        "can_commit": bool(parsed),
    }
    return stats, parsed, issues


def preview(db, body, settings: Settings) -> dict:
    stats, _, issues = _parse_rows(db, body, settings)
    return {
        **stats,
        "issues": issues[:50],
        "assumptions": ASSUMPTIONS,
    }


def _existing_import(db, key: str, content_hash: str):
    setting = db.get(models.Setting, key)
    if setting is None:
        return None
    value = setting.value if isinstance(setting.value, dict) else {}
    if value.get("content_hash") != content_hash:
        raise HTTPException(
            status_code=409,
            detail="request_id was used for a different CSV upload",
        )
    return {**value.get("result", {}), "replayed": True}


def commit_import(db, body, settings: Settings) -> dict:
    key = _request_key(body.request_id)
    content_hash = _content_hash(body)
    replay = _existing_import(db, key, content_hash)
    if replay is not None:
        return replay

    stats, rows, issues = _parse_rows(db, body, settings)
    imported_at = utc_now()
    batches: dict[int, models.Batch] = {}
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["product_id"], []).append(row)

    movements_created = 0
    stockout_events_created = 0
    imported_rows = 0
    for product_id, product_rows in grouped.items():
        sales_rows = [
            row for row in product_rows if row["quantity"] > 0 and not row["stockout"]
        ]
        total_sold = sum((row["quantity"] for row in sales_rows), Decimal("0"))
        if total_sold > 0:
            sku = sales_rows[0]["sku"]
            days = sorted(row["day"] for row in sales_rows)
            batch = models.Batch(
                product_id=product_id,
                batch_code=_batch_code(body.request_id, sku),
                quantity_received=total_sold,
                quantity_remaining=Decimal("0"),
                received_date=days[0],
                expiry_date=days[-1] + timedelta(days=1),
                unit_cost=Decimal("0"),
                status="CLOSED",
            )
            db.add(batch)
            db.flush()
            batches[product_id] = batch
            db.add(
                models.StockMovement(
                    product_id=product_id,
                    batch_id=batch.id,
                    movement_type="RECEIPT",
                    quantity_delta=total_sold,
                    occurred_at=datetime.combine(
                        days[0], time(hour=12), tzinfo=timezone.utc
                    ),
                    daypart=None,
                    reason="Imported historical sales",
                    actor_name="Sales import",
                    request_id=_movement_request_id(
                        body.request_id, sku, 0, "receipt"
                    ),
                )
            )
            movements_created += 1
            for index, row in enumerate(sales_rows, start=1):
                db.add(
                    models.StockMovement(
                        product_id=product_id,
                        batch_id=batch.id,
                        movement_type="SALE",
                        quantity_delta=-row["quantity"],
                        occurred_at=datetime.combine(
                            row["day"], time(hour=12), tzinfo=timezone.utc
                        ),
                        daypart=row["daypart"],
                        reason="Imported historical sales",
                        actor_name="Sales import",
                        request_id=_movement_request_id(
                            body.request_id, sku, index, "sale"
                        ),
                    )
                )
                movements_created += 1
        for index, row in enumerate(product_rows, start=1):
            if row["stockout"]:
                db.add(
                    models.StockoutEvent(
                        product_id=product_id,
                        business_date=row["day"],
                        daypart=row["daypart"],
                        requested_quantity=row["quantity"],
                        available_quantity=Decimal("0"),
                        source="SALES_IMPORT",
                        note=f"Imported stockout marker for {row['sku']}",
                    )
                )
                stockout_events_created += 1
            imported_rows += 1

    db.add(
        models.ActivityEvent(
            event_type="SALES_IMPORTED",
            entity_type="import",
            entity_id=0,
            actor_name="Sales import",
            reason=f"Imported {imported_rows} historical sales row(s)",
            payload={
                "request_id": body.request_id,
                "imported_rows": imported_rows,
                "batches_created": len(batches),
                "stockout_events_created": stockout_events_created,
            },
        )
    )

    result = {
        **stats,
        "request_id": body.request_id,
        "imported_rows": imported_rows,
        "batches_created": len(batches),
        "movements_created": movements_created,
        "stockout_events_created": stockout_events_created,
        "imported_at": imported_at,
        "data_version": 0,
        "replayed": False,
        "issues": issues[:50],
        "assumptions": ASSUMPTIONS,
    }
    db.add(
        models.Setting(
            key=key,
            value={
                "request_id": body.request_id,
                "content_hash": content_hash,
                "imported_at": imported_at.isoformat(),
                "result": json.loads(json.dumps(result, default=str)),
            },
        )
    )
    db.flush()
    result["data_version"] = data_version(db)
    setting = db.get(models.Setting, key)
    setting.value = {
        **setting.value,
        "result": json.loads(json.dumps(result, default=str)),
    }
    commit(db)
    return result
