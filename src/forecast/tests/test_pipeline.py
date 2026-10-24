from datetime import date

from forecast.contracts import Action
from forecast.pipeline import ForecastPipeline
from forecast.repository import InMemoryRepository
from forecast.synthetic import generate_synthetic_dataset

AS_OF = date(2026, 10, 20)


def test_pipeline_produces_all_demo_actions():
    dataset = generate_synthetic_dataset(seed=7, as_of_date=AS_OF)
    repository = InMemoryRepository.from_synthetic(dataset)
    recommendations = ForecastPipeline(repository).recommend_all(AS_OF)

    assert {item.action for item in recommendations} == {
        Action.BUY,
        Action.BAKE,
        Action.HOLD,
        Action.MARKDOWN,
    }
    assert all(item.approval_required for item in recommendations)
    assert all(item.forecast_run_id for item in recommendations)
    assert all(item.input_snapshot_id for item in recommendations)
    assert all(item.quantity >= 0 for item in recommendations)


def test_pipeline_can_limit_products():
    dataset = generate_synthetic_dataset(seed=7, as_of_date=AS_OF)
    repository = InMemoryRepository.from_synthetic(dataset)
    recommendations = ForecastPipeline(repository).recommend_all(
        AS_OF,
        product_skus=["sourdough"],
    )

    assert len(recommendations) == 1
    assert recommendations[0].product_sku == "sourdough"


def test_pipeline_does_not_mutate_inventory():
    dataset = generate_synthetic_dataset(seed=7, as_of_date=AS_OF)
    repository = InMemoryRepository.from_synthetic(dataset)
    before = tuple(repository.inventory())
    ForecastPipeline(repository).recommend_all(AS_OF)
    assert tuple(repository.inventory()) == before
