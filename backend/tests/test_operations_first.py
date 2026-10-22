import hashlib
import hmac
import json
from datetime import datetime, timezone


def test_supplier_email_draft(api):
    client, _app = api
    supplier = client.post(
        "/api/v1/suppliers",
        json={"name": "Flour Co", "email": "orders@flour.example"},
    ).json()
    product = client.post(
        "/api/v1/products",
        json={
            "sku": "FLOUR-1",
            "name": "Flour",
            "category": "bakery",
            "unit": "kg",
            "shelf_life_days": 30,
            "supplier_id": supplier["id"],
        },
    ).json()
    order = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "expected_date": "2026-12-01",
            "lines": [{"product_id": product["id"], "quantity": "10", "unit_cost": "2"}],
        },
    ).json()
    draft = client.get(f"/api/v1/purchase-orders/{order['id']}/supplier-email-draft")
    assert draft.status_code == 200
    assert draft.json()["recipient"] == "orders@flour.example"
    assert "Flour" in draft.json()["body"]
    assert draft.json()["mailto"].startswith("mailto:")


def test_market_day_is_exposed_on_weekly_planner(api):
    client, _app = api
    health = client.get("/health").json()
    from datetime import date, timedelta

    market_date = date.fromisoformat(health["business_date"]) + timedelta(days=1)
    created = client.post(
        "/api/v1/market-days",
        json={
            "market_date": market_date.isoformat(),
            "label": "Town market",
            "demand_multiplier": "1.25",
            "note": "Open early",
        },
    )
    assert created.status_code == 201
    planner = client.get("/api/v1/planner/week").json()
    first_day = next(day for day in planner["days"] if day["date"] == market_date.isoformat())
    assert first_day["market_day"]["label"] == "Town market"


def test_daily_sheet_is_read_only_and_serializable(catalog):
    client, _app, _supplier, _product = catalog
    response = client.get("/api/v1/daily-sheet")
    assert response.status_code == 200
    payload = response.json()
    assert payload["note"].startswith("Read-only")
    assert {"expiry_tasks", "actions", "deliveries", "bake_plan"}.issubset(payload)


def test_pos_sale_webhook_is_signed_and_idempotent(catalog):
    client, app, _supplier, product = catalog
    app.state.settings.pos_webhook_secret = "test-secret"
    today = client.get("/health").json()["business_date"]
    receipt = client.post(
        "/api/v1/batches",
        json={
            "product_id": product["id"],
            "batch_code": "POS-BATCH",
            "quantity_received": "5",
            "received_date": today,
            "expiry_date": "2099-01-01",
            "unit_cost": "1",
            "request_id": "pos-test-receipt",
            "actor_name": "Test",
            "actor_role": "owner",
            "reason": "test",
        },
    )
    assert receipt.status_code == 201
    body = json.dumps(
        {
            "event_id": "pos-event-1",
            "event_type": "sale",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"sku": product["sku"], "quantity": "2", "daypart": "midday"},
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(b"test-secret", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    headers = {"X-Buns-Timestamp": timestamp, "X-Buns-Signature": f"sha256={signature}"}
    response = client.post("/api/v1/webhooks/pos", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    replay = client.post("/api/v1/webhooks/pos", content=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
