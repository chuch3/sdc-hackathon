from __future__ import annotations

import pytest

pytest.importorskip("torch")
from datetime import date

from forecast.contracts import ForecastContext
from forecast.ml.catalog import build_training_dataset
from forecast.ml.dataset import build_training_examples, split_examples
from forecast.ml.evaluate import (
    baseline_predictions,
    promotion_gate,
    report_from_point_predictions,
)
from forecast.ml.features import (
    NUMERIC_FEATURE_DIM,
    FeatureEncoder,
    FeatureVocabulary,
)

AS_OF = date(2026, 10, 20)


def _context() -> ForecastContext:
    dataset = build_training_dataset(
        seed=9,
        as_of_date=AS_OF,
        days=140,
        products=12,
    )
    return ForecastContext(
        products={product.sku: product for product in dataset.products},
        sales_history=dataset.observations,
        overrides=dataset.overrides,
    )


def test_catalog_is_deterministic_and_sized() -> None:
    first = build_training_dataset(
        seed=9,
        as_of_date=AS_OF,
        days=140,
        products=12,
    )
    second = build_training_dataset(
        seed=9,
        as_of_date=AS_OF,
        days=140,
        products=12,
    )
    assert len(first.products) == 12
    assert len(first.inventory) == 12
    assert first.observations == second.observations
    assert first.products[0].sku == "sourdough"
    assert any(product.sku.startswith("sourdough-") for product in first.products)


def test_examples_and_time_split() -> None:
    context = _context()
    vocabulary = FeatureVocabulary.from_products(context.products.values())
    encoder = FeatureEncoder(
        vocabulary=vocabulary,
        mean=tuple(0.0 for _ in range(NUMERIC_FEATURE_DIM)),
        std=tuple(1.0 for _ in range(NUMERIC_FEATURE_DIM)),
    )
    examples = build_training_examples(context, encoder, min_history_days=28)
    assert examples
    assert all(item.target >= 0.0 for item in examples)
    assert all(len(item.features) == NUMERIC_FEATURE_DIM for item in examples)
    train, validation = split_examples(examples, 0.2)
    assert train and validation
    assert max(item.target_date for item in train) < min(
        item.target_date for item in validation
    )


def test_baseline_predictions_and_gate() -> None:
    context = _context()
    vocabulary = FeatureVocabulary.from_products(context.products.values())
    encoder = FeatureEncoder(
        vocabulary=vocabulary,
        mean=tuple(0.0 for _ in range(NUMERIC_FEATURE_DIM)),
        std=tuple(1.0 for _ in range(NUMERIC_FEATURE_DIM)),
    )
    examples = build_training_examples(context, encoder, min_history_days=28)
    predictions = baseline_predictions(context, examples[:50])
    assert len(predictions) == 50
    assert all(value >= 0.0 for value in predictions)
    targets = [item.target for item in examples[:50]]
    report = report_from_point_predictions(predictions, targets)
    decision = promotion_gate(report, report)
    assert decision.promote is False
    assert decision.reasons
