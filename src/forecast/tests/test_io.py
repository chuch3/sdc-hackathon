import json
from datetime import date, timedelta

from forecast.io import load_repository

AS_OF = date(2026, 1, 28)


def test_load_repository_from_json(tmp_path):
    start = AS_OF - timedelta(days=27)
    payload = {
        "products": [
            {
                "sku": "p1",
                "name": "Test product",
                "category": "dairy",
                "domain": "generic",
                "shelf_life_days": 7,
                "lead_time_days": 2,
                "moq": 10,
                "case_size": 10,
            }
        ],
        "sales_history": [
            {
                "product_sku": "p1",
                "business_date": (start + timedelta(days=offset)).isoformat(),
                "quantity": 10,
            }
            for offset in range(28)
        ],
        "inventory": [
            {
                "product_sku": "p1",
                "saleable_on_hand": 20,
                "remaining_shelf_life_days": 5,
            }
        ],
        "overrides": [
            {
                "business_date": (AS_OF + timedelta(days=1)).isoformat(),
                "multiplier": 1.2,
                "product_sku": "p1",
                "kind": "promo",
            }
        ],
    }
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload))

    repository = load_repository(path)

    assert len(repository.products()) == 1
    assert len(repository.sales_history()) == 28
    assert repository.inventory()[0].saleable_on_hand == 20
    assert repository.overrides()[0].multiplier == 1.2
