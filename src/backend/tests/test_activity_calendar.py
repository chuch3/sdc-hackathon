from datetime import timedelta

from sqlalchemy import select

from app import models


def _batch(client, app, product, *, code, quantity, days):
    today = app.state.settings.business_today()
    response = client.post(
        "/api/v1/batches",
        json={
            "product_id": product["id"],
            "batch_code": code,
            "quantity_received": quantity,
            "received_date": today.isoformat(),
            "expiry_date": (today + timedelta(days=days)).isoformat(),
            "unit_cost": "1.00",
            "actor_name": "Demo Owner",
            "actor_role": "owner",
            "reason": "Synthetic calendar batch",
            "request_id": f"req-{code}",
        },
    )
    assert response.status_code == 201, response.text


def _action(product, *, request_id, movement, quantity):
    return {
        "product_id": product["id"],
        "quantity": quantity,
        "movement_type": movement,
        "request_id": request_id,
        "actor_name": "Demo Owner",
        "actor_role": "owner",
        "reason": "Synthetic calendar action",
    }


def test_activity_calendar_returns_one_bucket_per_day(catalog):
    client, app, _, product = catalog
    _batch(client, app, product, code="CAL-1", quantity="10", days=2)
    client.post(
        "/api/v1/stock-actions",
        json=_action(product, request_id="cal-waste-1", movement="WASTE", quantity="3"),
    )
    response = client.get("/api/v1/analytics/activity-calendar", params={"days": 30})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["days_detail"]) == 30
    today = app.state.settings.business_today().isoformat()
    bucket = next(row for row in payload["days_detail"] if row["date"] == today)
    assert float(bucket["waste"]) == 3.0
    assert bucket["has_waste"] is True
    assert 0.0 <= float(bucket["intensity"]) <= 1.0
    empty = next(row for row in payload["days_detail"] if row["date"] != today)
    assert float(empty["sales"]) == 0.0
    assert float(empty["intensity"]) == 0.0


def test_activity_calendar_counts_stockouts(catalog):
    client, app, _, product = catalog
    _batch(client, app, product, code="CAL-2", quantity="2", days=2)
    rejected = client.post(
        "/api/v1/stock-actions",
        json=_action(product, request_id="cal-sale-1", movement="SALE", quantity="5"),
    )
    assert rejected.status_code == 409
    payload = client.get("/api/v1/analytics/activity-calendar", params={"days": 30}).json()
    today = app.state.settings.business_today().isoformat()
    bucket = next(row for row in payload["days_detail"] if row["date"] == today)
    assert bucket["stockouts"] == 1
    assert bucket["has_stockout"] is True


def test_recommendations_report_the_latest_decision(catalog):
    client, app, _, product = catalog
    decision = client.post(
        f"/api/v1/recommendations/{product['id']}/decision",
        json={
            "actor_name": "Demo Owner",
            "actor_role": "owner",
            "reason": "Approved from the dashboard",
            "decision": "APPROVED",
            "action": "HOLD",
            "quantity": "0",
            "note": "Looks fine",
        },
    )
    assert decision.status_code == 200, decision.text
    payload = client.get("/api/v1/recommendations").json()
    item = next(row for row in payload["recommendations"] if row["product_id"] == product["id"])
    assert item["decision"] == "APPROVED"
    assert item["decided_by"] == "Demo Owner"
    assert item["decided_at"] is not None

    client.post(
        f"/api/v1/recommendations/{product['id']}/decision",
        json={
            "actor_name": "Demo Owner",
            "actor_role": "owner",
            "reason": "Changed my mind",
            "decision": "REJECTED",
            "action": "HOLD",
            "quantity": "0",
            "note": "Not now",
        },
    )
    payload = client.get("/api/v1/recommendations").json()
    item = next(row for row in payload["recommendations"] if row["product_id"] == product["id"])
    assert item["decision"] == "REJECTED"


def test_edited_decision_updates_quantity(catalog):
    client, app, _, product = catalog
    edited_quantity = "3"
    
    client.post(
        f"/api/v1/recommendations/{product['id']}/decision",
        json={
            "actor_name": "Demo Owner",
            "actor_role": "owner",
            "reason": "Edited quantity from dashboard",
            "decision": "EDITED",
            "action": "HOLD",
            "quantity": edited_quantity,
        },
    )
    payload = client.get("/api/v1/recommendations").json()
    item = next(row for row in payload["recommendations"] if row["product_id"] == product["id"])
    assert item["decision"] == "EDITED"
    assert item["quantity"] == edited_quantity
    assert item["edited_quantity"] == edited_quantity
    
    with app.state.session_factory() as db:
        events = db.scalars(
            select(models.ActivityEvent).where(
                models.ActivityEvent.event_type == "RECOMMENDATION_EDITED"
            )
        ).all()
        assert len(events) == 1
        assert events[0].entity_id == product["id"]
    
    with app.state.session_factory() as db:
        events = db.scalars(
            select(models.ActivityEvent).where(
                models.ActivityEvent.event_type == "RECOMMENDATION_EDITED"
            )
        ).all()
        assert len(events) == 1
        assert events[0].entity_id == product["id"]
