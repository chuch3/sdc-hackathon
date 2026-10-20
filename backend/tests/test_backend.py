import os
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, inspect, select

from app import models
from app.db import build_engine
from scripts.seed import seed


def receipt(app, product, **changes):
    today = app.state.settings.business_today()
    data = {
        "product_id": product["id"],
        "batch_code": "TEST-BATCH-001",
        "quantity_received": "10.500",
        "received_date": today.isoformat(),
        "expiry_date": (today + timedelta(days=2)).isoformat(),
        "unit_cost": "2.50",
        "actor_name": "Demo Owner",
        "actor_role": "owner",
        "reason": "Approved receipt",
        "request_id": "test-receipt-001",
    }
    data.update(changes)
    return data


def test_health(api):
    client, _ = api
    assert client.get("/health").json()["schema"] == "ready"


def test_missing_schema_has_actionable_error(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(f"sqlite:///{(tmp_path / 'empty.db').as_posix()}")
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 503
        assert "alembic" in response.json()["next_step"]
    app.state.engine.dispose()


def test_duplicate_sku_rejected(catalog):
    client, _, _, product = catalog
    body = {key: value for key, value in product.items() if key not in {"id", "active"}}
    assert client.post("/api/v1/products", json=body).status_code == 409


def test_product_requires_existing_supplier(api):
    client, _ = api
    response = client.post(
        "/api/v1/products",
        json={
            "sku": "BAD",
            "name": "Bad",
            "category": "bakery",
            "unit": "loaf",
            "shelf_life_days": 2,
            "supplier_id": 999,
        },
    )
    assert response.status_code == 404


def test_negative_and_extra_quantity_rejected(catalog):
    client, app, _, product = catalog
    assert (
        client.post(
            "/api/v1/batches", json=receipt(app, product, quantity_received="-1")
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/batches", json=receipt(app, product, quantity_remaining="999")
        ).status_code
        == 422
    )


def test_invalid_expiry_rejected(catalog):
    client, app, _, product = catalog
    yesterday = app.state.settings.business_today() - timedelta(days=1)
    assert (
        client.post(
            "/api/v1/batches", json=receipt(app, product, expiry_date=yesterday.isoformat())
        ).status_code
        == 422
    )


def test_receipt_is_idempotent_and_ledger_matches(catalog):
    client, app, _, product = catalog
    body = receipt(app, product)
    first = client.post("/api/v1/batches", json=body)
    second = client.post("/api/v1/batches", json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    movements = client.get("/api/v1/movements").json()
    assert len(movements) == 1
    assert Decimal(movements[0]["quantity_delta"]) == Decimal("10.500")
    assert movements[0]["occurred_at"].endswith(("Z", "+00:00"))
    assert len(client.get("/api/v1/activity").json()) == 1


def test_reusing_key_with_changed_payload_rejected(catalog):
    client, app, _, product = catalog
    client.post("/api/v1/batches", json=receipt(app, product))
    response = client.post("/api/v1/batches", json=receipt(app, product, quantity_received="20"))
    assert response.status_code == 409
    assert len(client.get("/api/v1/movements").json()) == 1


def test_duplicate_batch_does_not_add_movement(catalog):
    client, app, _, product = catalog
    assert client.post("/api/v1/batches", json=receipt(app, product)).status_code == 201
    assert (
        client.post(
            "/api/v1/batches", json=receipt(app, product, request_id="new-request-same-batch")
        ).status_code
        == 409
    )
    assert len(client.get("/api/v1/movements").json()) == 1


def test_viewer_cannot_receive(catalog):
    client, app, _, product = catalog
    assert (
        client.post("/api/v1/batches", json=receipt(app, product, actor_role="viewer")).status_code
        == 403
    )
    assert client.get("/api/v1/batches").json() == []


def test_batch_hold_has_audit_record(catalog):
    client, app, _, product = catalog
    batch = client.post("/api/v1/batches", json=receipt(app, product)).json()
    result = client.patch(
        f"/api/v1/batches/{batch['id']}/status",
        json={"status": "QUARANTINED", "actor_name": "Demo Owner", "reason": "Pending inspection"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "QUARANTINED"
    assert client.get("/api/v1/activity").json()[0]["event_type"] == "BATCH_STATUS_CHANGED"


def test_archiving_preserves_stock_history(catalog):
    client, app, _, product = catalog
    client.post("/api/v1/batches", json=receipt(app, product))
    assert client.delete(f"/api/v1/products/{product['id']}").status_code == 204
    assert client.get("/api/v1/products").json() == []
    assert len(client.get("/api/v1/products?include_archived=true").json()) == 1
    assert len(client.get("/api/v1/movements").json()) == 1
    assert (
        client.post(
            "/api/v1/batches",
            json=receipt(app, product, batch_code="NEW", request_id="new-receipt"),
        ).status_code
        == 404
    )


def test_product_unit_cannot_change_after_receipt(catalog):
    client, app, _, product = catalog
    client.post("/api/v1/batches", json=receipt(app, product))
    body = {key: value for key, value in product.items() if key not in {"id", "active"}}
    body["unit"] = "kg"
    assert client.put(f"/api/v1/products/{product['id']}", json=body).status_code == 409


def test_purchase_approval_and_cancellation_affect_on_order(catalog):
    client, app, supplier, product = catalog
    tomorrow = (app.state.settings.business_today() + timedelta(days=1)).isoformat()
    body = {
        "supplier_id": supplier["id"],
        "expected_date": tomorrow,
        "lines": [{"product_id": product["id"], "quantity": "20", "unit_cost": "2"}],
    }
    po = client.post("/api/v1/purchase-orders", json=body).json()
    on_order = f"/api/v1/products/{product['id']}/on-order"
    assert Decimal(client.get(on_order).json()["quantity"]) == 0
    approve = f"/api/v1/purchase-orders/{po['id']}/approve"
    actor = {"actor_name": "Demo Owner", "actor_role": "viewer", "reason": "Reviewed"}
    assert client.post(approve, json=actor).status_code == 403
    actor["actor_role"] = "owner"
    approved = client.post(approve, json=actor)
    assert approved.status_code == 200
    assert approved.json()["approved_by"] == "Demo Owner"
    assert Decimal(client.get(on_order).json()["quantity"]) == 20
    assert client.post(approve, json=actor).status_code == 409
    cancel = f"/api/v1/purchase-orders/{po['id']}/cancel"
    assert client.post(cancel, json=actor).status_code == 200
    assert Decimal(client.get(on_order).json()["quantity"]) == 0


def test_overdue_purchase_not_treated_as_reliable_incoming_stock(catalog):
    client, app, supplier, product = catalog
    past = (app.state.settings.business_today() - timedelta(days=1)).isoformat()
    po = client.post(
        "/api/v1/purchase-orders",
        json={
            "supplier_id": supplier["id"],
            "expected_date": past,
            "lines": [{"product_id": product["id"], "quantity": "7", "unit_cost": "2"}],
        },
    ).json()
    client.post(
        f"/api/v1/purchase-orders/{po['id']}/approve",
        json={"actor_name": "Demo Owner", "reason": "Historical synthetic approval"},
    )
    result = client.get(f"/api/v1/products/{product['id']}/on-order").json()
    assert Decimal(result["quantity"]) == 0
    assert Decimal(result["overdue_quantity"]) == 7


def test_m2_and_m3_hooks_are_explicit_until_connected(catalog):
    client, _, _, product = catalog
    assert client.get(f"/api/v1/recommendations/{product['id']}").status_code == 501
    result = client.post(
        "/api/v1/stock-actions",
        json={
            "product_id": product["id"],
            "quantity": "2",
            "movement_type": "SALE",
            "request_id": "sale-demo-001",
            "actor_name": "Demo Owner",
            "reason": "Approved sale",
        },
    )
    assert result.status_code == 501


def test_recommendation_endpoint_uses_m3_service(catalog, monkeypatch):
    from app.services import recommendations

    client, _, _, product = catalog
    monkeypatch.setattr(
        recommendations,
        "recommend",
        lambda db, product_id, as_of: {
            "product_id": product_id,
            "action": "HOLD",
            "quantity": "0",
            "rationale": "Test result",
            "confidence": 0.6,
            "expiry_risk": "warning",
            "forecast_horizon_days": 3,
        },
    )
    result = client.get(f"/api/v1/recommendations/{product['id']}")
    assert result.status_code == 200
    assert result.json()["rationale"] == "Test result"


def test_csv_export_has_expected_headers(catalog):
    client, app, _, product = catalog
    client.post("/api/v1/batches", json=receipt(app, product))
    response = client.get("/api/v1/exports/inventory.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "available_today" in response.text
    assert "TEST-001" in response.text


def test_seed_repeatability_and_all_ledger_balances(api):
    _, app = api
    url = str(app.state.engine.url)
    seed(url)
    seed(url)
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(models.Product)) == 4
        assert db.scalar(select(func.count()).select_from(models.Batch)) == 80
        for batch in db.scalars(select(models.Batch)):
            total = db.scalar(
                select(func.sum(models.StockMovement.quantity_delta)).where(
                    models.StockMovement.batch_id == batch.id
                )
            )
            assert total == batch.quantity_remaining
        assert all(
            factor.kg_co2e_per_kg_waste == 0 for factor in db.scalars(select(models.SDGFactor))
        )


def test_real_migration_from_empty_database(tmp_path):
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    env = dict(os.environ, DATABASE_URL=url)
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = build_engine(url)
    try:
        inspector = inspect(engine)
        assert {"products", "batches", "stock_movements", "purchase_orders"}.issubset(
            inspector.get_table_names()
        )
        assert "ix_batch_fefo" in {index["name"] for index in inspector.get_indexes("batches")}
    finally:
        engine.dispose()
