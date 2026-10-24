from datetime import timedelta
from decimal import Decimal

from app import models


def test_no_products(api):
    client, _ = api
    body = client.get("/api/v1/onboarding/readiness").json()
    assert body["stage"] == "no_products"
    assert body["products_active"] == 0
    assert body["next_action"]["page"] == "Inventory"
    assert body["checks"][0]["ok"] is False


def test_products_without_sales(catalog):
    client, _, _, _ = catalog
    body = client.get("/api/v1/onboarding/readiness").json()
    assert body["stage"] == "no_sales"
    assert body["products_active"] == 1
    assert body["valid_days"] == 0
    assert body["next_action"]["page"] == "Settings"


def test_thin_history(catalog, add_sales_history):
    client, app, _, product = catalog
    add_sales_history(app, product["id"], days=5)
    body = client.get("/api/v1/onboarding/readiness").json()
    assert body["stage"] == "thin_history"
    assert body["valid_days"] == 5
    assert body["required_days"] == 14
    assert body["products_ready"] == 0


def test_ready_history(catalog, add_sales_history):
    client, app, _, product = catalog
    add_sales_history(app, product["id"], days=20)
    body = client.get("/api/v1/onboarding/readiness").json()
    assert body["stage"] == "ready"
    assert body["valid_days"] == 20
    assert body["products_ready"] == 1
    assert body["last_sale_date"] is not None
    assert all(check["ok"] for check in body["checks"])


def test_stockout_days_are_excluded(catalog, add_sales_history):
    client, app, _, product = catalog
    add_sales_history(app, product["id"], days=20)
    today = app.state.settings.business_today()
    with app.state.session_factory() as db:
        for offset in range(14, 4, -1):
            db.add(
                models.StockoutEvent(
                    product_id=product["id"],
                    business_date=today - timedelta(days=offset),
                    daypart="midday",
                    requested_quantity=Decimal("3"),
                    available_quantity=Decimal("0"),
                )
            )
        db.commit()
    body = client.get("/api/v1/onboarding/readiness").json()
    assert body["censored_days"] == 10
    assert body["valid_days"] == 10
    assert body["stage"] == "thin_history"
    assert body["checks"][3]["key"] == "stockouts"
    assert "10 day(s) excluded" in body["checks"][3]["detail"]


def test_stockouts_only_censor_their_own_product(catalog, add_sales_history):
    client, app, supplier, product = catalog
    second = client.post(
        "/api/v1/products",
        json={
            "sku": "TEST-002",
            "name": "Test Milk",
            "category": "dairy",
            "unit": "litre",
            "shelf_life_days": 5,
            "supplier_id": supplier["id"],
            "domain": "bakery",
        },
    ).json()
    add_sales_history(app, product["id"], days=20)
    add_sales_history(app, second["id"], days=20, prefix="HIST2")
    today = app.state.settings.business_today()
    with app.state.session_factory() as db:
        for offset in range(14, 4, -1):
            db.add(
                models.StockoutEvent(
                    product_id=product["id"],
                    business_date=today - timedelta(days=offset),
                    daypart="midday",
                    requested_quantity=Decimal("3"),
                    available_quantity=Decimal("0"),
                )
            )
        db.commit()
    body = client.get("/api/v1/onboarding/readiness").json()
    assert body["censored_days"] == 10
    assert body["valid_days"] == 20
    assert body["products_ready"] == 1
    assert body["stage"] == "ready"
