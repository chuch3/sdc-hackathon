from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import models
from app.db import Base
from app.main import create_app


@pytest.fixture
def api(tmp_path):
    app = create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        yield client, app
    app.state.engine.dispose()


@pytest.fixture
def add_sales_history():
    """Append closed batches and SALE movements straight into the ledger."""

    def _add(
        app,
        product_id,
        *,
        days=20,
        quantity=10,
        movement_type="SALE",
        daypart="midday",
        prefix="HIST",
    ):
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
                        reason="Synthetic test history",
                        actor_name="Test Suite",
                    )
                )
            db.commit()

    return _add


@pytest.fixture
def catalog(api):
    client, app = api
    supplier = client.post("/api/v1/suppliers", json={"name": "Synthetic Supplier"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "sku": "TEST-001",
            "name": "Test Bread",
            "category": "bakery",
            "unit": "loaf",
            "shelf_life_days": 3,
            "supplier_id": supplier["id"],
            "domain": "bakery",
            "allergens": ["gluten"],
        },
    ).json()
    return client, app, supplier, product
