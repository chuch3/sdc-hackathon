from datetime import date, timedelta

from forecast.contracts import (
    Action,
    Confidence,
    DailyForecast,
    DataQuality,
    Domain,
    ForecastResult,
    InventoryPosition,
    Product,
    ReasonCode,
)
from forecast.policies import policies_for
from forecast.reorder import ReorderService

AS_OF = date(2026, 1, 28)


def make_product(domain: Domain = Domain.GENERIC) -> Product:
    return Product(
        sku="p1",
        name="Test product",
        category="bakery" if domain is Domain.BAKERY else "dairy",
        domain=domain,
        unit="unit",
        lead_time_days=2,
        review_period_days=1,
        moq=10,
        case_size=10,
        service_level=0.95,
        near_expiry_threshold_days=2,
    )


def make_forecast(
    total: float,
    horizon: int,
    error_std: float = 10.0,
    actionable: bool = True,
) -> ForecastResult:
    daily_quantity = total / horizon
    daily = tuple(
        DailyForecast(
            forecast_date=AS_OF + timedelta(days=offset),
            quantity=daily_quantity,
            lower=max(0.0, daily_quantity - error_std),
            upper=daily_quantity + error_std,
        )
        for offset in range(1, horizon + 1)
    )
    return ForecastResult(
        product_sku="p1",
        as_of_date=AS_OF,
        horizon_days=horizon,
        daily=daily,
        total_quantity=total,
        total_lower=max(0.0, total - error_std),
        total_upper=total + error_std,
        error_std=error_std,
        confidence=Confidence.MEDIUM,
        model_name="test",
        model_version="1",
        reason_codes=(ReasonCode.BASELINE_28D,),
        why=("why one", "why two", "why three"),
        data_quality=DataQuality(
            window_days=28,
            history_days=28,
            valid_days=28,
            censored_days=0,
            last_sale_date=AS_OF,
            cold_start=False,
            stale=False,
        ),
        forecast_run_id="run-1",
        input_snapshot_id="snapshot-1",
        actionable=actionable,
    )


def test_buy_recommendation_rounds_to_moq():
    product = make_product()
    position = InventoryPosition("p1", saleable_on_hand=20, remaining_shelf_life_days=7)
    forecast = make_forecast(100, 2)
    shelf_forecast = make_forecast(100, 2)

    recommendation = ReorderService().recommend(
        product,
        position,
        forecast,
        policies_for(product),
        shelf_forecast,
    )

    assert recommendation.action is Action.BUY
    assert recommendation.quantity == 100
    assert recommendation.quantity <= recommendation.calculation["fresh_cap"]
    assert recommendation.approval_required is True
    assert recommendation.calculation["reorder_point"] > 0


def test_bakery_recommendation_bakes():
    product = make_product(Domain.BAKERY)
    position = InventoryPosition("p1", saleable_on_hand=20, remaining_shelf_life_days=7)
    forecast = make_forecast(100, 2)

    recommendation = ReorderService().recommend(
        product,
        position,
        forecast,
        policies_for(product),
        make_forecast(100, 2),
    )

    assert recommendation.action is Action.BAKE


def test_hold_when_stock_covers_demand():
    product = make_product()
    position = InventoryPosition("p1", saleable_on_hand=200, remaining_shelf_life_days=7)
    forecast = make_forecast(20, 2)

    recommendation = ReorderService().recommend(
        product,
        position,
        forecast,
        policies_for(product),
        make_forecast(20, 2),
    )

    assert recommendation.action is Action.HOLD
    assert recommendation.quantity == 0
    assert ReasonCode.NO_REORDER in recommendation.reason_codes


def test_markdown_when_near_expiry_surplus():
    product = make_product()
    position = InventoryPosition("p1", saleable_on_hand=50, remaining_shelf_life_days=1)
    forecast = make_forecast(20, 2)
    shelf_forecast = make_forecast(20, 1)

    recommendation = ReorderService().recommend(
        product,
        position,
        forecast,
        policies_for(product),
        shelf_forecast,
    )

    assert recommendation.action is Action.MARKDOWN
    assert recommendation.quantity == 30
    assert ReasonCode.NEAR_EXPIRY_SURPLUS in recommendation.reason_codes


def test_markdown_never_recommends_zero_units():
    """A fractional surplus still recommends one unit, not a no-op markdown."""
    product = make_product()
    position = InventoryPosition("p1", saleable_on_hand=20.4, remaining_shelf_life_days=1)
    forecast = make_forecast(20, 2)
    shelf_forecast = make_forecast(20, 1)

    recommendation = ReorderService().recommend(
        product,
        position,
        forecast,
        policies_for(product),
        shelf_forecast,
    )

    assert recommendation.action is Action.MARKDOWN
    assert recommendation.quantity == 1


def test_blocked_forecast_returns_hold():
    product = make_product()
    position = InventoryPosition("p1", saleable_on_hand=20, remaining_shelf_life_days=7)
    forecast = make_forecast(100, 2, actionable=False)

    recommendation = ReorderService().recommend(
        product,
        position,
        forecast,
        policies_for(product),
    )

    assert recommendation.action is Action.HOLD
    assert recommendation.quantity == 0
    assert ReasonCode.BLOCKED_DATA_QUALITY in recommendation.reason_codes


def test_recommendation_never_auto_approves():
    product = make_product()
    position = InventoryPosition("p1", saleable_on_hand=20, remaining_shelf_life_days=7)
    recommendation = ReorderService().recommend(
        product,
        position,
        make_forecast(100, 2),
        policies_for(product),
        make_forecast(100, 2),
    )
    assert recommendation.approval_required is True
    assert not hasattr(recommendation, "approved_by")
