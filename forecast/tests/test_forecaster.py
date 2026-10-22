from datetime import date, timedelta

import pytest

from forecast.baseline import BaselineForecaster
from forecast.contracts import (
    CalendarOverride,
    Confidence,
    Domain,
    ForecastContext,
    ForecastRequest,
    Product,
    ReasonCode,
    SalesObservation,
)

AS_OF = date(2026, 1, 28)


def make_product(
    sku: str = "p1",
    category: str = "dairy",
    domain: Domain = Domain.GENERIC,
    **kwargs,
) -> Product:
    return Product(
        sku=sku,
        name=sku,
        category=category,
        domain=domain,
        **kwargs,
    )


def constant_history(
    product: Product,
    days: int,
    quantity: float,
    end: date = AS_OF,
) -> list[SalesObservation]:
    start = end - timedelta(days=days - 1)
    return [
        SalesObservation(
            product_sku=product.sku,
            business_date=start + timedelta(days=offset),
            quantity=quantity,
        )
        for offset in range(days)
    ]


def test_baseline_constant_demand():
    product = make_product()
    context = ForecastContext(
        products={product.sku: product},
        sales_history=tuple(constant_history(product, 28, 10)),
    )
    result = BaselineForecaster().forecast(
        ForecastRequest(product.sku, AS_OF, 7),
        context,
    )

    assert result.total_quantity == pytest.approx(70)
    assert result.confidence is Confidence.HIGH
    assert result.actionable is True
    assert ReasonCode.BASELINE_28D in result.reason_codes
    assert result.data_quality.valid_days == 28


def test_censored_stockout_days_are_excluded():
    product = make_product()
    history = constant_history(product, 28, 10)
    history[-1] = SalesObservation(
        product_sku=product.sku,
        business_date=AS_OF,
        quantity=0,
        is_stockout_censored=True,
    )
    context = ForecastContext(
        products={product.sku: product},
        sales_history=tuple(history),
    )
    result = BaselineForecaster().forecast(
        ForecastRequest(product.sku, AS_OF, 7),
        context,
    )

    assert result.total_quantity == pytest.approx(70)
    assert result.data_quality.censored_days == 1
    assert ReasonCode.CENSORED_EXCLUDED in result.reason_codes


def test_cold_start_uses_category_fallback():
    existing = make_product(sku="old")
    new = make_product(sku="new")
    history = constant_history(existing, 28, 20)
    history += constant_history(new, 3, 10)
    context = ForecastContext(
        products={existing.sku: existing, new.sku: new},
        sales_history=tuple(history),
    )
    result = BaselineForecaster().forecast(
        ForecastRequest(new.sku, AS_OF, 2),
        context,
    )

    assert result.data_quality.cold_start is True
    assert result.actionable is True
    assert result.confidence is Confidence.LOW
    assert ReasonCode.COLD_START in result.reason_codes
    assert result.total_quantity > 0


def test_holiday_override_is_applied():
    product = make_product()
    context = ForecastContext(
        products={product.sku: product},
        sales_history=tuple(constant_history(product, 28, 10)),
        overrides=(
            CalendarOverride(
                business_date=AS_OF + timedelta(days=1),
                multiplier=2.0,
                product_sku=product.sku,
            ),
        ),
    )
    result = BaselineForecaster().forecast(
        ForecastRequest(product.sku, AS_OF, 1),
        context,
    )

    assert result.total_quantity == pytest.approx(20)
    assert ReasonCode.HOLIDAY_OVERRIDE in result.reason_codes


def test_bakery_daypart_share_is_applied():
    product = make_product(
        domain=Domain.BAKERY,
        daypart_shares={"morning": 0.5, "evening": 0.5},
    )
    context = ForecastContext(
        products={product.sku: product},
        sales_history=tuple(constant_history(product, 28, 10)),
    )
    result = BaselineForecaster().forecast(
        ForecastRequest(product.sku, AS_OF, 1, daypart="morning"),
        context,
    )

    assert result.total_quantity == pytest.approx(5)
    assert ReasonCode.DAYPART_SHARE in result.reason_codes


def test_missing_history_blocks_action():
    product = make_product()
    context = ForecastContext(products={product.sku: product}, sales_history=())
    result = BaselineForecaster().forecast(
        ForecastRequest(product.sku, AS_OF, 3),
        context,
    )

    assert result.total_quantity == 0
    assert result.actionable is False
    assert result.confidence is Confidence.LOW
    assert ReasonCode.NO_HISTORY in result.reason_codes
