from datetime import timedelta


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
            "reason": "Synthetic analytics batch",
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
        "reason": "Synthetic analytics action",
    }


def test_impact_summary_labels_estimates_and_counts_waste(catalog):
    client, app, _, product = catalog
    _batch(client, app, product, code="IMPACT-1", quantity="10", days=2)
    client.post(
        "/api/v1/stock-actions",
        json=_action(product, request_id="waste-1", movement="WASTE", quantity="4"),
    )
    response = client.get("/api/v1/analytics/impact")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert float(payload["waste_units"]) == 4.0
    assert float(payload["estimated_waste_kg"]) == 4.0
    assert payload["estimated_meals"] == 0.0
    assert "estimate" in payload["assumption"].lower()


def test_bakery_plan_requires_approval_and_seasonal_advice_is_safe(catalog):
    client, app, _, product = catalog
    today = app.state.settings.business_today()
    plan = client.get("/api/v1/bakery/bake-plan", params={"plan_date": today.isoformat()})
    assert plan.status_code == 200, plan.text
    item = next(row for row in plan.json() if row["product_id"] == product["id"])
    assert item["approval_required"] is True
    assert item["slots"]
    assert sum(float(slot["quantity"]) for slot in item["slots"]) == float(
        item["total_quantity"]
    )

    saved = client.post(
        "/api/v1/bakery/bake-plan",
        json={
            "plan_date": today.isoformat(),
            "product_id": product["id"],
            "actor_name": "Demo Owner",
            "actor_role": "owner",
            "reason": "Bake plan test",
        },
    )
    assert saved.status_code == 201, saved.text
    approved = client.post(
        f"/api/v1/bakery/bake-plan/{product['id']}/approve",
        params={"plan_date": today.isoformat()},
        json={
            "actor_name": "Demo Owner",
            "actor_role": "owner",
            "reason": "Bake plan approval test",
        },
    )
    assert approved.status_code == 200, approved.text

    advice = client.get("/api/v1/bakery/seasonal-advice")
    assert advice.status_code == 200
    assert isinstance(advice.json(), list)
