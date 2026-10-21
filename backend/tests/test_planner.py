from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app import models
from app.services import weekly_planner

CARD_ORDER = weekly_planner.CARD_ORDER


@pytest.fixture
def shop(api):
    """One generic product with twenty days of sales history and no stock."""
    client, app = api
    supplier = client.post("/api/v1/suppliers", json={"name": "Synthetic Supplier"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "sku": "MILK-1",
            "name": "Test Milk",
            "category": "dairy",
            "unit": "litre",
            "shelf_life_days": 5,
            "supplier_id": supplier["id"],
            "lead_time_days": 2,
            "domain": "generic",
        },
    ).json()
    add_history(app, product["id"], days=20, quantity=10)
    return client, app, supplier, product


def add_history(
    app,
    product_id,
    *,
    days=20,
    quantity=10,
    movement_type="SALE",
    daypart="midday",
    prefix="HIST",
):
    """Insert synthetic daily movements straight into the ledger."""
    with app.state.session_factory() as db:
        today = app.state.settings.business_today()
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            batch = models.Batch(
                product_id=product_id,
                batch_code=f"{prefix}-{day.isoformat()}",
                quantity_received=Decimal(quantity),
                quantity_remaining=Decimal("0"),
                received_date=day,
                expiry_date=day + timedelta(days=1),
                unit_cost=Decimal("2.00"),
                status="CLOSED",
            )
            db.add(batch)
            db.flush()
            db.add(
                models.StockMovement(
                    product_id=product_id,
                    batch_id=batch.id,
                    movement_type=movement_type,
                    quantity_delta=Decimal(-quantity),
                    occurred_at=datetime(
                        day.year, day.month, day.day, 4, tzinfo=timezone.utc
                    ),
                    daypart=daypart,
                    reason="Synthetic planner history",
                    actor_name="Test Suite",
                )
            )
        db.commit()


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
        "reason": "Synthetic planner batch",
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
                "reason": "Planner test status",
            },
        )
        assert changed.status_code == 200, changed.text
    return batch


def make_order(client, app, supplier, product, *, expected_date, quantity="12", approve=True):
    order = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "expected_date": expected_date.isoformat(),
            "lines": [
                {"product_id": product["id"], "quantity": quantity, "unit_cost": "2.00"}
            ],
        },
    ).json()
    if approve:
        client.post(
            f"/api/v1/purchase-orders/{order['id']}/approve",
            json={
                "actor_name": "Demo Owner",
                "actor_role": "owner",
                "reason": "Approved for the planner test",
            },
        )
    return order


def cards_of(day, kind):
    return [card for card in day["cards"] if card["kind"] == kind]


def test_planner_returns_seven_days_from_tomorrow(shop):
    client, app, _, _ = shop
    today = app.state.settings.business_today()
    payload = client.get("/api/v1/planner/week").json()
    assert payload["day_count"] == 7
    assert payload["as_of"] == today.isoformat()
    assert payload["start_date"] == (today + timedelta(days=1)).isoformat()
    assert payload["end_date"] == (today + timedelta(days=7)).isoformat()
    assert [day["date"] for day in payload["days"]] == [
        (today + timedelta(days=offset)).isoformat() for offset in range(1, 8)
    ]
    assert [day["weekday"] for day in payload["days"]] == [
        (today + timedelta(days=offset)).strftime("%A") for offset in range(1, 8)
    ]


def test_planner_is_deterministic_and_orders_cards_consistently(shop):
    client, _, _, _ = shop
    first = client.get("/api/v1/planner/week").json()
    second = client.get("/api/v1/planner/week").json()
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second
    for day in first["days"]:
        ranks = [CARD_ORDER[card["kind"]] for card in day["cards"]]
        assert ranks == sorted(ranks)


def test_demand_uses_only_sale_movements(shop):
    client, app, _, product = shop
    add_history(
        app,
        product["id"],
        days=1,
        quantity=100,
        movement_type="WASTE",
        prefix="WASTE",
    )
    add_batch(client, app, product, code="STOCK", quantity="100", days=10)
    payload = client.get("/api/v1/planner/week").json()
    first_day = payload["days"][0]
    assert float(first_day["projection"]["expected_sales"]) == pytest.approx(10.0, abs=0.5)


def test_expired_stock_is_never_saleable_and_is_written_off(shop):
    client, app, _, product = shop
    add_batch(client, app, product, code="EXPIRED", quantity="50", days=-1, received_days=6)
    payload = client.get("/api/v1/planner/week").json()
    first_day = payload["days"][0]
    write_offs = cards_of(first_day, "WRITE_OFF")
    assert write_offs, "expired stock must produce a write-off card"
    assert float(write_offs[0]["quantity"]) == 50.0
    assert float(first_day["projection"]["starting_stock"]) == 0.0


def test_quarantined_stock_is_excluded_from_saleable_stock(shop):
    client, app, _, product = shop
    add_batch(
        client, app, product, code="HOLD", quantity="40", days=1, status="QUARANTINED"
    )
    payload = client.get("/api/v1/planner/week").json()
    first_day = payload["days"][0]
    assert float(first_day["projection"]["starting_stock"]) == 0.0
    write_offs = cards_of(first_day, "WRITE_OFF")
    assert any(float(card["quantity"]) == 40.0 for card in write_offs)


def test_near_expiry_stock_produces_a_sell_first_card(shop):
    client, app, _, product = shop
    add_batch(client, app, product, code="SOON", quantity="12", days=1)
    payload = client.get("/api/v1/planner/week").json()
    sell_first = cards_of(payload["days"][0], "SELL_FIRST")
    assert sell_first, "stock expiring tomorrow must produce a sell-first card"
    assert float(sell_first[0]["quantity"]) == 12.0
    assert sell_first[0]["deadline"] == (
        app.state.settings.business_today() + timedelta(days=1)
    ).isoformat()


def test_draft_orders_never_arrive(shop):
    client, app, supplier, product = shop
    today = app.state.settings.business_today()
    make_order(
        client,
        app,
        supplier,
        product,
        expected_date=today + timedelta(days=2),
        approve=False,
    )
    payload = client.get("/api/v1/planner/week").json()
    assert not any(day["orders_due"] for day in payload["days"])
    assert not any(cards_of(day, "RECEIVE_ORDER") for day in payload["days"])


def test_approved_orders_arrive_on_the_expected_date(shop):
    client, app, supplier, product = shop
    today = app.state.settings.business_today()
    make_order(client, app, supplier, product, expected_date=today + timedelta(days=2))
    payload = client.get("/api/v1/planner/week").json()
    arrival_day = payload["days"][1]
    assert arrival_day["date"] == (today + timedelta(days=2)).isoformat()
    assert arrival_day["orders_due"], "the approved order must be listed on its arrival day"
    assert arrival_day["orders_due"][0]["overdue"] is False
    assert cards_of(arrival_day, "RECEIVE_ORDER")


def test_overdue_approved_orders_arrive_on_the_first_day(shop):
    client, app, supplier, product = shop
    today = app.state.settings.business_today()
    make_order(client, app, supplier, product, expected_date=today - timedelta(days=2))
    payload = client.get("/api/v1/planner/week").json()
    first_day = payload["days"][0]
    assert first_day["orders_due"]
    assert first_day["orders_due"][0]["overdue"] is True
    assert cards_of(first_day, "RECEIVE_ORDER")


def test_demand_above_available_stock_projects_a_stockout(shop):
    client, app, _, product = shop
    add_batch(client, app, product, code="SMALL", quantity="4", days=4)
    payload = client.get("/api/v1/planner/week").json()
    first_day = payload["days"][0]
    assert float(first_day["projection"]["expected_sales"]) == 4.0
    assert float(first_day["projection"]["unmet_demand"]) == 6.0
    stockouts = cards_of(first_day, "STOCKOUT")
    assert stockouts
    assert float(stockouts[0]["quantity"]) == 6.0
    assert first_day["kpis"]["stockout_risk"] == "high"


def test_a_shortage_is_reported_once_with_its_span(shop):
    client, app, _, product = shop
    add_batch(client, app, product, code="TINY", quantity="1", days=4)
    payload = client.get("/api/v1/planner/week").json()
    stockout_days = [day for day in payload["days"] if cards_of(day, "STOCKOUT")]
    assert len(stockout_days) == 1, "the same shortage must not be repeated every day"
    card = cards_of(stockout_days[0], "STOCKOUT")[0]
    assert card["quantity"] == "9.000"
    assert "in stock at the start of the day" in " ".join(card["why"])
    assert any("Short from" in line for line in card["why"])
    assert float(card["calculation"]["available_at_start"]) == 1.0


def test_planner_never_writes_to_the_ledger(shop):
    client, app, supplier, product = shop
    add_batch(client, app, product, code="SOON", quantity="12", days=1)
    today = app.state.settings.business_today()
    make_order(client, app, supplier, product, expected_date=today)
    with app.state.session_factory() as db:
        before = {
            "movements": db.scalar(select(func.count()).select_from(models.StockMovement)),
            "batches": db.scalar(select(func.count()).select_from(models.Batch)),
            "orders": db.scalar(select(func.count()).select_from(models.PurchaseOrder)),
        }
    client.get("/api/v1/planner/week")
    with app.state.session_factory() as db:
        after = {
            "movements": db.scalar(select(func.count()).select_from(models.StockMovement)),
            "batches": db.scalar(select(func.count()).select_from(models.Batch)),
            "orders": db.scalar(select(func.count()).select_from(models.PurchaseOrder)),
        }
    assert before == after


def test_planner_rejects_a_start_date_in_the_past(shop):
    client, app, _, _ = shop
    today = app.state.settings.business_today()
    response = client.get(
        f"/api/v1/planner/week?start={(today - timedelta(days=1)).isoformat()}"
    )
    assert response.status_code == 422


def test_projection_consumes_the_earliest_expiry_batch_first():
    """The shared FEFO allocator decides which batch a sale comes from."""
    today = date(2026, 10, 20)
    plan = weekly_planner.ProductPlan(
        product=None,
        sku="TEST-1",
        name="Test",
        unit="litre",
        domain="generic",
        threshold=3,
        lead_time_days=2,
        batches=[
            weekly_planner.ProjectedBatch(
                id=1,
                product_id=1,
                batch_code="EARLY",
                expiry_date=today + timedelta(days=1),
                received_date=today,
                quantity=Decimal("5"),
                unit_cost=Decimal("2.00"),
            ),
            weekly_planner.ProjectedBatch(
                id=2,
                product_id=1,
                batch_code="LATE",
                expiry_date=today + timedelta(days=5),
                received_date=today,
                quantity=Decimal("20"),
                unit_cost=Decimal("2.00"),
            ),
        ],
        expired_before=[],
        quarantined=[],
        demand={today + timedelta(days=1): Decimal("8")},
        arrivals={},
        recommendation=None,
        confidence=0.65,
    )
    weekly_planner._project(plan, [today + timedelta(days=1)], today, today + timedelta(days=1))
    state = plan.days[today + timedelta(days=1)]
    assert state.expected_sales == Decimal("8")
    assert plan.batches[0].quantity == Decimal("0")
    assert plan.batches[1].quantity == Decimal("17")
