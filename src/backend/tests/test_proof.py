from datetime import timedelta
from decimal import Decimal

from app import models


def test_proof_reports_accuracy_observed_and_projection(catalog, add_sales_history):
    client, app, _, product = catalog
    add_sales_history(app, product["id"], days=20, quantity=10)
    today = app.state.settings.business_today()
    with app.state.session_factory() as db:
        db.add(
            models.StockoutEvent(
                product_id=product["id"],
                business_date=today - timedelta(days=5),
                daypart="midday",
                requested_quantity=Decimal("4"),
                available_quantity=Decimal("0"),
            )
        )
        db.commit()

    response = client.get("/api/v1/analytics/proof?days=14")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accuracy"]["observations"] == 13
    assert body["accuracy"]["excluded_censored"] == 1
    assert body["accuracy"]["products_evaluated"] == 1
    assert body["accuracy"]["coverage_80"] is not None
    assert body["accuracy"]["wape"] is not None
    assert body["observed"]["sales_units"] == 130
    assert body["observed"]["stockout_events"] == 1
    assert body["projection"]["annualised_waste_units"] == 0
    assert body["model"]["interval"] == "80%"
    assert len(body["assumptions"]) >= 4


def test_proof_without_history_is_safe(api):
    client, _ = api
    response = client.get("/api/v1/analytics/proof?days=14")
    assert response.status_code == 200
    body = response.json()
    assert body["accuracy"]["observations"] == 0
    assert body["accuracy"]["wape"] is None
    assert body["accuracy"]["coverage_80"] is None
    assert body["projection"]["annualised_waste_units"] == 0
