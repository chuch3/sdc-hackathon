import pytest
from fastapi.testclient import TestClient

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
