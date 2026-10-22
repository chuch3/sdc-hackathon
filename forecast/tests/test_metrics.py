import pytest

from forecast.metrics import bias, evaluate_metrics, mae, mape, wape


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
