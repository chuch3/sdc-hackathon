from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app import models


def _csv(rows, header="date,sku,quantity,daypart,stockout"):
    return "\n".join([header, *rows]) + "\n"


def test_preview_accepts_aliases_and_mixed_dates(catalog):
    client, app, _, product = catalog
    today = app.state.settings.business_today()
    rows = [
        f"{(today - timedelta(days=2)).isoformat()},{product['sku']},4,morning,false",
        (
            f"{(today - timedelta(days=1)).strftime('%d/%m/%Y')},"
            f"{product['sku']},5,midday,no"
        ),
        f"{(today - timedelta(days=1)).isoformat()},NOPE-001,2,midday,false",
        f"{(today - timedelta(days=1)).isoformat()},{product['sku']},-3,midday,false",
    ]
    body = client.post(
        "/api/v1/imports/sales/preview",
        json={
            "csv_text": _csv(
                rows,
                "business_date,item,qty,part_of_day,out_of_stock",
            )
        },
    ).json()
    assert body["can_commit"] is True
    assert body["total_rows"] == 4
    assert body["valid_rows"] == 2
    assert body["invalid_rows"] == 2
    assert body["unknown_skus"] == ["NOPE-001"]
    assert body["date_start"] == (today - timedelta(days=2)).isoformat()
    assert body["date_end"] == (today - timedelta(days=1)).isoformat()
    assert body["valid_days"] == 2
    assert body["mapping"]["date"] == "business_date"
    assert body["mapping"]["sku"] == "item"


def test_commit_is_idempotent_and_does_not_touch_saleable_stock(catalog):
    client, app, _, product = catalog
    today = app.state.settings.business_today()
    rows = [
        f"{(today - timedelta(days=offset)).isoformat()},{product['sku']},3,morning,false"
        for offset in range(14, 0, -1)
    ]
    rows.append(
        f"{(today - timedelta(days=1)).isoformat()},{product['sku']},0,midday,true"
    )
    payload = {
        "csv_text": _csv(rows),
        "request_id": "import-idempotent-001",
    }
    first = client.post("/api/v1/imports/sales/commit", json=payload)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["imported_rows"] == 15
    assert body["batches_created"] == 1
    assert body["movements_created"] == 15
    assert body["stockout_events_created"] == 1
    assert body["replayed"] is False

    positions = client.get("/api/v1/inventory/positions").json()
    assert sum(float(item["saleable_on_hand"]) for item in positions) == 0

    with app.state.session_factory() as db:
        batch = db.scalar(select(models.Batch))
        assert batch.status == "CLOSED"
        assert batch.quantity_remaining == 0
        assert batch.quantity_received == Decimal("42.000")
        assert batch.unit_cost == 0
        assert batch.batch_code.startswith("IMPORT-HIST-import-idempotent-001-")
        movement_count = db.scalar(select(func.count()).select_from(models.StockMovement))
        assert movement_count == 15
        receipt = db.scalar(
            select(models.StockMovement).where(
                models.StockMovement.movement_type == "RECEIPT"
            )
        )
        assert receipt.quantity_delta == Decimal("42.000")

    replay = client.post("/api/v1/imports/sales/commit", json=payload)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(models.StockMovement)) == 15
        assert db.scalar(select(func.count()).select_from(models.StockoutEvent)) == 1

    same_id_different_data = client.post(
        "/api/v1/imports/sales/commit",
        json={
            "csv_text": _csv(
                [
                    f"{(today - timedelta(days=1)).isoformat()},"
                    f"{product['sku']},9,midday,false"
                ]
            ),
            "request_id": "import-idempotent-001",
        },
    )
    assert same_id_different_data.status_code == 409


def test_commit_unlocks_readiness(catalog):
    client, app, _, product = catalog
    today = app.state.settings.business_today()
    rows = [
        f"{(today - timedelta(days=16 - offset)).isoformat()},{product['sku']},2,morning,false"
        for offset in range(1, 16)
    ]
    response = client.post(
        "/api/v1/imports/sales/commit",
        json={"csv_text": _csv(rows), "request_id": "import-readiness-001"},
    )
    assert response.status_code == 200, response.text
    readiness = client.get("/api/v1/onboarding/readiness").json()
    assert readiness["valid_days"] == 15
    assert readiness["stage"] == "ready"
    assert readiness["last_import_at"] is not None


def test_commit_rejects_future_dates(catalog):
    client, app, _, product = catalog
    tomorrow = app.state.settings.business_today() + timedelta(days=1)
    response = client.post(
        "/api/v1/imports/sales/commit",
        json={
            "csv_text": _csv([f"{tomorrow.isoformat()},{product['sku']},2,morning,false"]),
            "request_id": "import-future-001",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid_rows"] == 0
    assert body["invalid_rows"] == 1
    assert body["movements_created"] == 0
