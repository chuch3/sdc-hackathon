from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("yaml")
from datetime import date, timedelta
from pathlib import Path

import torch

from forecast.contracts import ForecastContext
from forecast.ml.config import ModelConfig
from forecast.ml.features import (
    NUMERIC_FEATURE_DIM,
    FeatureEncoder,
    FeatureVocabulary,
    build_product_history,
)
from forecast.ml.model import (
    DemandNet,
    build_model,
    load_checkpoint,
    pinball_loss,
    predict_dates,
    save_checkpoint,
)
from forecast.synthetic import generate_synthetic_dataset


def _context(days: int = 40) -> ForecastContext:
    dataset = generate_synthetic_dataset(
        seed=11,
        as_of_date=date(2026, 10, 20),
        days=days,
    )
    return ForecastContext(
        products={product.sku: product for product in dataset.products},
        sales_history=dataset.observations,
        overrides=dataset.overrides,
    )


def _encoder(context: ForecastContext) -> FeatureEncoder:
    vocabulary = FeatureVocabulary.from_products(context.products.values())
    return FeatureEncoder(
        vocabulary=vocabulary,
        mean=tuple(0.0 for _ in range(NUMERIC_FEATURE_DIM)),
        std=tuple(1.0 for _ in range(NUMERIC_FEATURE_DIM)),
    )


def test_pinball_loss_is_zero_for_perfect_quantiles() -> None:
    targets = torch.tensor([5.0, 10.0])
    predictions = torch.tensor(
        [
            [5.0, 5.0, 5.0],
            [10.0, 10.0, 10.0],
        ]
    )
    loss = pinball_loss(predictions, targets, (0.1, 0.5, 0.9))
    assert float(loss.item()) == pytest.approx(0.0)


def test_model_forward_shape() -> None:
    model = DemandNet(
        num_skus=4,
        num_categories=3,
        numeric_dim=NUMERIC_FEATURE_DIM,
        quantiles=(0.1, 0.5, 0.9),
        hidden_sizes=(8,),
    )
    output = model(
        torch.tensor([1, 2]),
        torch.tensor([1, 2]),
        torch.zeros(2, NUMERIC_FEATURE_DIM),
    )
    assert output.shape == (2, 3)


def test_checkpoint_roundtrip_and_prediction_range(tmp_path: Path) -> None:
    context = _context()
    encoder = _encoder(context)
    config = ModelConfig(hidden_sizes=(8,), embedding_dim=4, dropout=0.0)
    model = build_model(
        num_skus=encoder.vocabulary.num_skus,
        num_categories=encoder.vocabulary.num_categories,
        numeric_dim=NUMERIC_FEATURE_DIM,
        config=config,
    )
    checkpoint_path = tmp_path / "model.pt"
    save_checkpoint(checkpoint_path, model, encoder, config, {"WAPE": 0.2})
    checkpoint = load_checkpoint(checkpoint_path)
    product = context.products["sourdough"]
    history = build_product_history(context, product.sku)
    anchor = date(2026, 10, 19)
    predictions = predict_dates(
        checkpoint,
        product,
        history,
        anchor,
        [anchor + timedelta(days=1), anchor + timedelta(days=2)],
        context.overrides,
    )
    assert len(predictions) == 2
    for row in predictions:
        assert len(row) == 3
        assert list(row) == sorted(row)
        assert all(value >= 0.0 for value in row)
    assert checkpoint.metrics["WAPE"] == pytest.approx(0.2)


def test_missing_checkpoint_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_checkpoint(tmp_path / "missing.pt")
