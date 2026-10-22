from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Sequence

from .contracts import ForecastContext, ForecastRequest
from .forecasting import Forecaster


@dataclass(frozen=True)
class MetricResult:
    name: str
    value: float | None
    n: int
    excluded: int = 0
    note: str = ""


def _validate(actual: Sequence[float], forecast: Sequence[float]) -> None:
    if len(actual) != len(forecast):
        raise ValueError("actual and forecast must have the same length")


def mae(actual: Sequence[float], forecast: Sequence[float]) -> MetricResult:
    _validate(actual, forecast)
    if not actual:
        return MetricResult("MAE", None, 0, note="no observations")
    value = sum(abs(a - f) for a, f in zip(actual, forecast)) / len(actual)
    return MetricResult("MAE", value, len(actual))


def mape(actual: Sequence[float], forecast: Sequence[float]) -> MetricResult:
    _validate(actual, forecast)
    pairs = [(a, f) for a, f in zip(actual, forecast) if a != 0]
    if not pairs:
        return MetricResult(
            "MAPE",
            None,
            0,
            excluded=len(actual),
            note="MAPE is undefined when all actuals are zero",
        )
    value = sum(abs(a - f) / abs(a) for a, f in pairs) / len(pairs)
    return MetricResult(
        "MAPE",
        value,
        len(pairs),
        excluded=len(actual) - len(pairs),
        note="zero-demand days excluded",
    )


def bias(actual: Sequence[float], forecast: Sequence[float]) -> MetricResult:
    _validate(actual, forecast)
    if not actual:
        return MetricResult("bias", None, 0, note="no observations")
    value = sum(f - a for a, f in zip(actual, forecast)) / len(actual)
    return MetricResult(
        "bias",
        value,
        len(actual),
        note="positive means over-forecasting",
    )


def wape(actual: Sequence[float], forecast: Sequence[float]) -> MetricResult:
    _validate(actual, forecast)
    denominator = sum(abs(a) for a in actual)
    if denominator == 0:
        return MetricResult(
            "WAPE",
            None,
            len(actual),
            note="WAPE is undefined when total actual demand is zero",
        )
    value = sum(abs(a - f) for a, f in zip(actual, forecast)) / denominator
    return MetricResult("WAPE", value, len(actual))


def evaluate_metrics(
    actual: Sequence[float],
    forecast: Sequence[float],
) -> dict[str, MetricResult]:
    return {
        "MAE": mae(actual, forecast),
        "MAPE": mape(actual, forecast),
        "bias": bias(actual, forecast),
        "WAPE": wape(actual, forecast),
    }


@dataclass(frozen=True)
class BacktestObservation:
    product_sku: str
    business_date: date
    actual: float
    forecast: float
    lower: float
    upper: float


def backtest_observations(
    forecaster: Forecaster,
    context: ForecastContext,
    as_of: date,
    horizon_days: int,
    product_skus: Iterable[str] | None = None,
) -> list[BacktestObservation]:
    """Per-day actual and forecast rows, excluding stockout-censored days."""
    skus = list(product_skus or sorted(context.products))
    observations: list[BacktestObservation] = []
    for sku in skus:
        if sku not in context.products:
            continue
        result = forecaster.forecast(
            ForecastRequest(
                product_sku=sku,
                as_of_date=as_of,
                horizon_days=horizon_days,
            ),
            context,
        )
        actual_by_date: dict[date, float] = defaultdict(float)
        censored_dates: set[date] = set()
        end = as_of + timedelta(days=horizon_days)
        for observation in context.sales_history:
            if (
                observation.product_sku == sku
                and as_of < observation.business_date <= end
            ):
                actual_by_date[observation.business_date] += observation.quantity
                if observation.is_stockout_censored:
                    censored_dates.add(observation.business_date)
        for item in result.daily:
            if item.forecast_date in censored_dates:
                continue
            observations.append(
                BacktestObservation(
                    product_sku=sku,
                    business_date=item.forecast_date,
                    actual=actual_by_date.get(item.forecast_date, 0.0),
                    forecast=item.quantity,
                    lower=item.lower,
                    upper=item.upper,
                )
            )
    return observations


def backtest_forecaster(
    forecaster: Forecaster,
    context: ForecastContext,
    as_of: date,
    horizon_days: int,
    product_skus: Iterable[str] | None = None,
) -> dict[str, dict[str, MetricResult]]:
    observations = backtest_observations(
        forecaster, context, as_of, horizon_days, product_skus
    )
    grouped: dict[str, list[BacktestObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.product_sku].append(observation)
    results: dict[str, dict[str, MetricResult]] = {}
    for sku, rows in grouped.items():
        results[sku] = evaluate_metrics(
            [row.actual for row in rows],
            [row.forecast for row in rows],
        )
    return results
