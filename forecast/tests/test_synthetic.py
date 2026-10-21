from datetime import date

from forecast.contracts import Domain
from forecast.synthetic import generate_synthetic_dataset


def test_generator_is_deterministic():
    first = generate_synthetic_dataset(seed=7, as_of_date=date(2026, 10, 20))
    second = generate_synthetic_dataset(seed=7, as_of_date=date(2026, 10, 20))
    third = generate_synthetic_dataset(seed=8, as_of_date=date(2026, 10, 20))

    assert first.observations == second.observations
    assert first.observations != third.observations


def test_generator_has_bakery_dayparts_and_censored_days():
    dataset = generate_synthetic_dataset(seed=7, as_of_date=date(2026, 10, 20))
    bakery_skus = {
        product.sku for product in dataset.products if product.domain is Domain.BAKERY
    }
    bakery_observations = [
        observation
        for observation in dataset.observations
        if observation.product_sku in bakery_skus
    ]

    assert bakery_observations
    assert all(observation.daypart is not None for observation in bakery_observations)
    assert any(
        observation.is_stockout_censored
        for observation in dataset.observations
    )


def test_generator_has_all_demo_action_inputs():
    dataset = generate_synthetic_dataset(seed=7, as_of_date=date(2026, 10, 20))
    assert {product.domain for product in dataset.products} == {
        Domain.GENERIC,
        Domain.BAKERY,
    }
    assert len(dataset.inventory) == len(dataset.products)
    assert dataset.overrides
