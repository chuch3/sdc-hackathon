from __future__ import annotations

import pytest

pytest.importorskip("torch")
pytest.importorskip("yaml")
from datetime import date, timedelta
from pathlib import Path

from forecast.contracts import (
    ForecastContext,
    ForecastRequest,
    Product,
    ReasonCode,
    SalesObservation,
)
from forecast.ml.config import ModelConfig
from forecast.ml.features import (
    NUMERIC_FEATURE_DIM,
    FeatureEncoder,
    FeatureVocabulary,
)
from forecast.ml.forecaster import MLForecaster
from forecast.ml.model import build_model, save_checkpoint
from forecast.synthetic import generate_synthetic_dataset


def _context(days: int = 120) -> ForecastContext:
    dataset = generate_synthetic_dataset(
        seed=5,
        as_of_date=date(2026, 10, 20),
        days=days,
    )
    return ForecastContext(
        products={product.sku: product for product in dataset.products},
        sales_history=dataset.observations,
        overrides=dataset.overrides,
    )


def _write_checkpoint(
    path: Path,
    context: ForecastContext,
    products: tuple[Product, ...] | None = None,
) -> None:
    vocabulary = FeatureVocabulary.from_products(products or context.products.values())
    encoder = FeatureEncoder(
        vocabulary=vocabulary,
        mean=tuple(0.0 for _ in range(NUMERIC_FEATURE_DIM)),
        std=tuple(1.0 for _ in range(NUMERIC_FEATURE_DIM)),
    )
    config = ModelConfig(hidden_sizes=(8,), embedding_dim=4, dropout=0.0)
    model = build_model(
        num_skus=vocabulary.num_skus,
        num_categories=vocabulary.num_categories,
        numeric_dim=NUMERIC_FEATURE_DIM,
        config=config,
    )
    save_checkpoint(path, model, encoder, config, {"WAPE": 0.2})


def _request(sku: str, as_of: date) -> ForecastRequest:
    return ForecastRequest(product_sku=sku, as_of_date=as_of, horizon_days=2)


def test_missing_checkpoint_falls_back_to_baseline(tmp_path: Path) -> None:
    context = _context()
    forecaster = MLForecaster(tmp_path / "missing.pt")
    result = forecaster.forecast(
        _request("sourdough", date(2026, 10, 20)),
        context,
    )
    assert result.model_name == "baseline-28d"
    assert ReasonCode.ML_FALLBACK_BASELINE in result.reason_codes


def test_known_product_uses_ml_forecast(tmp_path: Path) -> None:
    context = _context()
    checkpoint_path = tmp_path / "model.pt"
    _write_checkpoint(checkpoint_path, context)
    forecaster = MLForecaster(checkpoint_path)
    result = forecaster.forecast(
        _request("sourdough", date(2026, 10, 20)),
        context,
    )
    assert result.model_name == "mlp-quantile"
    assert ReasonCode.ML_FORECAST in result.reason_codes
    assert ReasonCode.ML_FALLBACK_BASELINE not in result.reason_codes
    assert len(result.daily) == 2
    assert all(item.lower <= item.quantity <= item.upper for item in result.daily)


def test_unseen_product_falls_back(tmp_path: Path) -> None:
    context = _context()
    checkpoint_path = tmp_path / "model.pt"
    known = (context.products["sourdough"],)
    _write_checkpoint(checkpoint_path, context, products=known)
    forecaster = MLForecaster(checkpoint_path)
    result = forecaster.forecast(
        _request("milk", date(2026, 10, 20)),
        context,
    )
    assert result.model_name == "baseline-28d"
    assert ReasonCode.ML_FALLBACK_BASELINE in result.reason_codes


def test_stale_history_falls_back(tmp_path: Path) -> None:
    product = Product(
        sku="bread",
        name="Bread",
        category="bakery",
        shelf_life_days=2,
    )
    as_of = date(2026, 10, 20)
    context = ForecastContext(
        products={product.sku: product},
        sales_history=(
            SalesObservation(product.sku, as_of - timedelta(days=10), 20.0),
        ),
    )
    checkpoint_path = tmp_path / "model.pt"
    _write_checkpoint(checkpoint_path, context)
    forecaster = MLForecaster(checkpoint_path)
    result = forecaster.forecast(_request(product.sku, as_of), context)
    assert result.model_name == "baseline-28d"
    assert ReasonCode.ML_FALLBACK_BASELINE in result.reason_codes
    assert result.data_quality.stale
