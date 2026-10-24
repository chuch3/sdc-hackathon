from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app import models


def add_batch(client, app, product, *, code, quantity, days, received_days=0, status=None):
    today = app.state.settings.business_today()
    body = {
        "product_id": product["id"],
        "batch_code": code,
        "quantity_received": quantity,
        "received_date": (today - timedelta(days=received_days)).isoformat(),
        "expiry_date": (today + timedelta(days=days)).isoformat(),
        "unit_cost": "2.00",
        "actor_name": "Demo Owner",
        "actor_role": "owner",
        "reason": "Synthetic M2 batch",
        "request_id": f"req-{code}",
    }
    response = client.post("/api/v1/batches", json=body)
    assert response.status_code == 201, response.text
    batch = response.json()
    if status:
        changed = client.patch(
            f"/api/v1/batches/{batch['id']}/status",
            json={
                "status": status,
                "actor_name": "Demo Owner",
                "actor_role": "owner",
                "reason": "M2 test status",
            },
        )
        assert changed.status_code == 200, changed.text
        batch = changed.json()
    return batch


def stock_action(product, quantity, movement="SALE", request_id="sale-1", role="owner"):
    return {
        "product_id": product["id"],
        "quantity": quantity,
        "movement_type": movement,
        "request_id": request_id,
        "daypart": "midday",
        "actor_name": "Demo Owner",
        "actor_role": role,
        "reason": "Synthetic stock action",
    }


def test_fefo_allocates_earliest_expiry_first(catalog):
    client, app, _, product = catalog
    add_batch(client, app, product, code="LATE", quantity="10", days=5)
    add_batch(client, app, product, code="EARLY", quantity="5", days=1)
    response = client.post("/api/v1/stock-actions", json=stock_action(product, "7"))
    assert response.status_code == 201, response.text
    payload = response.json()
    assert [item["batch_code"] for item in payload["allocations"]] == ["EARLY", "LATE"]
    assert [Decimal(item["quantity"]) for item in payload["allocations"]] == [
        Decimal("5"),
        Decimal("2"),
    ]
    movements = client.get(f"/api/v1/movements?product_id={product['id']}").json()
    sales = [row for row in movements if row["movement_type"] == "SALE"]
    assert len(sales) == 2
    assert sum(Decimal(row["quantity_delta"]) for row in sales) == Decimal("-7")


def test_sale_excludes_expired_and_quarantined_stock(catalog):
    client, app, _, product = catalog
    add_batch(
        client, app, product, code="EXPIRED", quantity="4", days=-1, received_days=5
    )
    add_batch(client, app, product, code="HOLD", quantity="4", days=3, status="QUARANTINED")
    add_batch(client, app, product, code="SAFE", quantity="3", days=2)
    response = client.post("/api/v1/stock-actions", json=stock_action(product, "5"))
    assert response.status_code == 409
    assert "available 3" in response.json()["detail"]
    sold = client.post("/api/v1/stock-actions", json=stock_action(product, "3", request_id="sale-2"))
    assert sold.status_code == 201
    assert sold.json()["allocations"][0]["batch_code"] == "SAFE"


def test_waste_can_remove_expired_stock_but_donation_cannot(catalog):
    client, app, _, product = catalog
    add_batch(client, app, product, code="EXPIRED", quantity="4", days=-1, received_days=5)
    donation = client.post(
        "/api/v1/stock-actions",
        json=stock_action(product, "1", movement="DONATION", request_id="donate-1"),
    )
    assert donation.status_code == 409
    waste = client.post(
        "/api/v1/stock-actions",
        json=stock_action(product, "1", movement="WASTE", request_id="waste-1"),
    )
    assert waste.status_code == 201, waste.text
    assert waste.json()["allocations"][0]["batch_code"] == "EXPIRED"


def test_sale_is_idempotent_and_changed_payload_conflicts(catalog):
    client, app, _, product = catalog
    add_batch(client, app, product, code="SAFE", quantity="10", days=2)
    body = stock_action(product, "3", request_id="idem-1")
    first = client.post("/api/v1/stock-actions", json=body)
    second = client.post("/api/v1/stock-actions", json=body)
    assert first.status_code == second.status_code == 201
    assert second.json()["replayed"] is True
    assert client.get(f"/api/v1/batches?product_id={product['id']}").json()[0][
        "quantity_remaining"
    ] == "7.000"
    changed = client.post(
        "/api/v1/stock-actions", json=stock_action(product, "4", request_id="idem-1")
    )
    assert changed.status_code == 409
    assert client.get("/api/v1/stock-actions/idem-1").status_code == 200


def test_viewer_cannot_record_sale_but_staff_can(catalog):
    client, app, _, product = catalog
    add_batch(client, app, product, code="SAFE", quantity="4", days=2)
    denied = client.post(
        "/api/v1/stock-actions",
        json=stock_action(product, "1", request_id="sale-viewer", role="viewer"),
    )
    assert denied.status_code == 403
    allowed = client.post(
        "/api/v1/stock-actions",
        json=stock_action(product, "1", request_id="sale-staff", role="staff"),
    )
    assert allowed.status_code == 201


def test_insufficient_sale_records_stockout_event(catalog):
    client, app, _, product = catalog
    add_batch(client, app, product, code="SAFE", quantity="2", days=2)
    response = client.post("/api/v1/stock-actions", json=stock_action(product, "5"))
    assert response.status_code == 409
    with app.state.session_factory() as db:
        event = db.scalar(select(models.StockoutEvent))
        assert event is not None
        assert event.requested_quantity == Decimal("5.000")
        assert event.available_quantity == Decimal("2.000")


def test_adjustments_are_signed_and_ledger_balanced(catalog):
    client, app, _, product = catalog
    batch = add_batch(client, app, product, code="SAFE", quantity="10", days=2)
    body = {
        "product_id": product["id"],
        "batch_id": batch["id"],
        "quantity_delta": "-2",
        "request_id": "adjust-1",
        "actor_name": "Demo Owner",
        "actor_role": "owner",
        "reason": "Synthetic shrinkage",
    }
    response = client.post("/api/v1/stock-adjustments", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["allocated_quantity"] == "2.000"
    with app.state.session_factory() as db:
        row = db.get(models.Batch, batch["id"])
        total = db.scalar(
            select(models.StockMovement).where(models.StockMovement.batch_id == batch["id"])
        )
        assert row.quantity_remaining == Decimal("8.000")
        assert total is not None


def test_partial_and_full_purchase_order_receipt(catalog):
    client, app, supplier, product = catalog
    today = app.state.settings.business_today()
    po = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "expected_date": (today + timedelta(days=1)).isoformat(),
            "lines": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2"}],
        },
    ).json()
    client.post(
        f"/api/v1/purchase-orders/{po['id']}/approve",
        json={"actor_name": "Demo Owner", "actor_role": "owner", "reason": "Approved"},
    )
    line_id = po["lines"][0]["id"]
    first = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={
            "request_id": "po-receipt-1",
            "actor_name": "Demo Owner",
            "actor_role": "owner",
            "reason": "Partial delivery",
            "lines": [
                {
                    "purchase_order_line_id": line_id,
                    "quantity": "4",
                    "received_date": today.isoformat(),
                    "expiry_date": (today + timedelta(days=3)).isoformat(),
                }
            ],
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "APPROVED"
    assert Decimal(client.get(f"/api/v1/products/{product['id']}/on-order").json()["quantity"]) == 6
    second = client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        json={
            "request_id": "po-receipt-2",
            "actor_name": "Demo Owner",
            "actor_role": "owner",
            "reason": "Final delivery",
            "lines": [
                {
                    "purchase_order_line_id": line_id,
                    "quantity": "6",
                    "received_date": today.isoformat(),
                    "expiry_date": (today + timedelta(days=3)).isoformat(),
                }
            ],
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["status"] == "RECEIVED"


def test_expiry_buckets_and_positions(catalog):
    client, app, _, product = catalog
    add_batch(client, app, product, code="EXPIRED", quantity="2", days=-1, received_days=5)
    add_batch(client, app, product, code="CRITICAL", quantity="3", days=0)
    add_batch(client, app, product, code="WARNING", quantity="4", days=2)
    add_batch(client, app, product, code="HEALTHY", quantity="5", days=9)
    buckets = client.get("/api/v1/expiry/buckets").json()
    assert Decimal(buckets["totals"]["expired"]) == 2
    assert Decimal(buckets["totals"]["critical"]) == 3
    assert Decimal(buckets["totals"]["warning"]) == 4
    assert Decimal(buckets["totals"]["healthy"]) == 5
    position = client.get("/api/v1/inventory/positions").json()[0]
    assert Decimal(position["physical_on_hand"]) == 14
    assert Decimal(position["saleable_on_hand"]) == 12
    assert Decimal(position["expired_quantity"]) == 2
    assert 0 < position["risk_score"] <= 1


def test_expiry_scan_writes_audit_event(catalog):
    client, app, _, product = catalog
    add_batch(client, app, product, code="CRITICAL", quantity="3", days=0)
    result = client.post("/api/v1/expiry/scan")
    assert result.status_code == 200
    assert result.json()["batches"] == 1
    assert client.get("/api/v1/activity").json()[0]["event_type"] == "EXPIRY_SCAN"
