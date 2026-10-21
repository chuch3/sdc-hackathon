from __future__ import annotations

from datetime import date, timedelta

from forecast.contracts import ForecastContext, SalesObservation
from forecast.ml.features import (
    NUMERIC_FEATURE_DIM,
    NUMERIC_FEATURE_NAMES,
    FeatureEncoder,
    FeatureVocabulary,
    build_product_history,
    raw_feature_vector,
)
from forecast.synthetic import generate_synthetic_dataset


def _context(days: int = 45) -> ForecastContext:
    dataset = generate_synthetic_dataset(
        seed=7,
        as_of_date=date(2026, 10, 20),
        days=days,
    )
    return ForecastContext(
        products={product.sku: product for product in dataset.products},
        sales_history=dataset.observations,
        overrides=dataset.overrides,
    )


def test_history_aggregates_dayparts_and_excludes_censored() -> None:
    context = _context()
    history = build_product_history(context, "sourdough")
    day = date(2026, 10, 20)
    expected = sum(
        item.quantity
        for item in context.sales_history
        if item.product_sku == "sourdough"
        and item.business_date == day
        and not item.is_stockout_censored
    )
    assert history.value(day) == expected
    assert history.last_sale_date is not None


def test_raw_feature_vector_shape_and_lags() -> None:
    context = _context()
    product = context.products["milk"]
    history = build_product_history(context, product.sku)
    anchor = date(2026, 10, 19)
    target = anchor + timedelta(days=1)
    features = raw_feature_vector(
        product,
        history,
        target,
        anchor,
        context.overrides,
    )
    assert len(features) == NUMERIC_FEATURE_DIM
    lag_1 = features[NUMERIC_FEATURE_NAMES.index("lag_1")]
    lag_7 = features[NUMERIC_FEATURE_NAMES.index("lag_7")]
    assert lag_1 == history.value(anchor)
    assert lag_7 == history.value(anchor - timedelta(days=6))
    assert features[NUMERIC_FEATURE_NAMES.index("horizon")] == 1.0


def test_encoder_roundtrip_and_normalization() -> None:
    context = _context()
    vocabulary = FeatureVocabulary.from_products(context.products.values())
    encoder = FeatureEncoder(
        vocabulary=vocabulary,
        mean=tuple(0.0 for _ in range(NUMERIC_FEATURE_DIM)),
        std=tuple(1.0 for _ in range(NUMERIC_FEATURE_DIM)),
    )
    product = context.products["baguette"]
    history = build_product_history(context, product.sku)
    target = date(2026, 10, 20)
    sku_index, category_index, features = encoder.encode(
        product,
        history,
        target,
        target - timedelta(days=1),
        context.overrides,
    )
    assert sku_index > 0
    assert category_index > 0
    assert len(features) == NUMERIC_FEATURE_DIM
    restored = FeatureEncoder.from_dict(encoder.to_dict())
    assert restored.vocabulary == vocabulary
    assertion_features = restored.encode(
        product,
        history,
        target,
        target - timedelta(days=1),
        context.overrides,
    )[2]
    assert assertion_features == features


def test_censored_day_is_never_used_as_a_lag() -> None:
    product = generate_synthetic_dataset(
        seed=3,
        as_of_date=date(2026, 10, 20),
        days=40,
    ).products[0]
    day = date(2026, 10, 20)
    context = ForecastContext(
        products={product.sku: product},
        sales_history=(
            SalesObservation(product.sku, day - timedelta(days=1), 10.0),
            SalesObservation(
                product.sku,
                day,
                99.0,
                is_stockout_censored=True,
            ),
        ),
    )
    history = build_product_history(context, product.sku)
    assert history.censored == frozenset({day})
    assert history.value(day) == 10.0
    assert history.value(day + timedelta(days=1)) == 10.0
