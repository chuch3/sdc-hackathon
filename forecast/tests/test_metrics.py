from datetime import date, timedelta

import pytest

from forecast.baseline import BaselineForecaster
from forecast.contracts import ForecastContext, Product, SalesObservation
from forecast.metrics import (
    backtest_observations,
    bias,
    evaluate_metrics,
    mae,
    mape,
    wape,
)


def test_metrics_hand_computed():
    actual = [10, 0, 20]
    forecast = [12, 0, 18]

    assert mae(actual, forecast).value == pytest.approx(4 / 3)
    assert mape(actual, forecast).value == pytest.approx(0.15)
    assert mape(actual, forecast).n == 2
    assert mape(actual, forecast).excluded == 1
    assert bias(actual, forecast).value == pytest.approx(0.0)
    assert wape(actual, forecast).value == pytest.approx(4 / 30)


def test_mape_undefined_when_all_actuals_zero():
    result = mape([0, 0], [1, 2])
    assert result.value is None
    assert result.excluded == 2


def test_wape_undefined_when_total_zero():
    assert wape([0, 0], [1, 2]).value is None


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        mae([1], [1, 2])


def test_evaluate_metrics_returns_scorecards():
    results = evaluate_metrics([10, 10], [12, 8])
    assert set(results) == {"MAE", "MAPE", "bias", "WAPE"}
    assert results["bias"].value == pytest.approx(0.0)


def test_backtest_observations_keep_bounds_and_exclude_censored_days():
    as_of = date(2026, 1, 28)
    product = Product(
        sku="p1",
        name="Test product",
        category="dairy",
        unit="unit",
        lead_time_days=2,
        review_period_days=1,
    )
    history = [
        SalesObservation(
            product_sku="p1",
            business_date=as_of - timedelta(days=offset),
            quantity=10.0,
        )
        for offset in range(28, -1, -1)
    ]
    censored_date = as_of + timedelta(days=3)
    history.extend(
        [
            SalesObservation(
                product_sku="p1",
                business_date=as_of + timedelta(days=offset),
                quantity=10.0,
                is_stockout_censored=(as_of + timedelta(days=offset) == censored_date),
            )
            for offset in range(1, 8)
        ]
    )
    context = ForecastContext(products={"p1": product}, sales_history=tuple(history))
    observations = backtest_observations(
        BaselineForecaster(), context, as_of, horizon_days=7
    )
    assert len(observations) == 6
    assert censored_date not in {row.business_date for row in observations}
    assert all(row.lower <= row.forecast <= row.upper for row in observations)
    assert all(row.actual == pytest.approx(10.0) for row in observations)
