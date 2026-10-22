from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app import models
from app.config import Settings
from app.services import analytics
from app.services.forecast_repository import build_pipeline
from app.services.timeutil import utc_start

ASSUMPTIONS = [
    "Accuracy is a single-cutoff holdout backtest. It shows how the current engine "
    "would have predicted the recent window, not a guarantee of future accuracy.",
    "Stockout-censored product-days are excluded from accuracy so an empty shelf is "
    "not scored as low demand.",
    "An 80% interval is expected to contain the actual on roughly 80% of days.",
    "Observed impact treats one stock unit as one kilogram and uses the configured, "
    "illustrative SDG factors. These are estimates, not certified measurements.",
    "The annual projection is a run-rate of the observed window, not a causal saving "
    "claim. Use the switchback plan in docs/AB_TEST_PLAN.md for attribution.",
]


def _metric(metrics: dict, name: str) -> float | None:
    result = metrics[name]
    if result.value is None:
        return None
    return round(float(result.value), 4)


def build_proof(db, settings: Settings, days: int = 14) -> dict:
    days = max(1, min(days, 60))
    as_of = settings.business_today()
    cutoff = as_of - timedelta(days=days + 1)
    pipeline = build_pipeline(db, as_of, settings)
    context = pipeline.build_context(None)
    from forecast.metrics import backtest_observations, evaluate_metrics

    observations = backtest_observations(
        pipeline.forecaster,
        context,
        cutoff,
        days,
    )
    actual = [row.actual for row in observations]
    forecast = [row.forecast for row in observations]
    metrics = evaluate_metrics(actual, forecast)
    covered = sum(1 for row in observations if row.lower <= row.actual <= row.upper)
    coverage = covered / len(observations) if observations else None
    excluded_censored = sum(
        1
        for observation in context.sales_history
        if observation.is_stockout_censored
        and cutoff < observation.business_date < as_of
    )

    impact = analytics.impact_summary(db, days, as_of=as_of, settings=settings)
    window_start = as_of - timedelta(days=days - 1)
    sales_units = db.scalar(
        select(func.coalesce(func.sum(-models.StockMovement.quantity_delta), 0)).where(
            models.StockMovement.movement_type == "SALE",
            models.StockMovement.occurred_at >= utc_start(window_start, settings),
        )
    )
    stockout_events = db.scalar(
        select(func.count())
        .select_from(models.StockoutEvent)
        .where(models.StockoutEvent.business_date >= window_start)
    )
    waste_units = Decimal(impact["waste_units"])
    donation_units = Decimal(impact["donation_units"])
    co2e = Decimal(impact["estimated_co2e_kg"])
    meals = Decimal(impact["estimated_meals"])

    return {
        "as_of": as_of.isoformat(),
        "window_days": days,
        "cutoff": cutoff.isoformat(),
        "accuracy": {
            "wape": _metric(metrics, "WAPE"),
            "bias": _metric(metrics, "bias"),
            "mae": _metric(metrics, "MAE"),
            "coverage_80": None if coverage is None else round(coverage, 4),
            "observations": len(observations),
            "excluded_censored": excluded_censored,
            "products_evaluated": len({row.product_sku for row in observations}),
        },
        "observed": {
            "sales_units": float(sales_units or 0),
            "waste_units": float(waste_units),
            "donation_units": float(donation_units),
            "estimated_waste_kg": float(impact["estimated_waste_kg"]),
            "estimated_donation_kg": float(impact["estimated_donation_kg"]),
            "estimated_co2e_kg": float(co2e),
            "estimated_meals": float(meals),
            "stockout_events": int(stockout_events or 0),
        },
        "projection": {
            "basis": (
                "Annual run-rate of the observed window. This is a scale reference, "
                "not a promised saving."
            ),
            "annualised_waste_units": round(float(waste_units) / days * 365, 2),
            "annualised_donation_units": round(float(donation_units) / days * 365, 2),
            "annualised_estimated_co2e_kg": round(float(co2e) / days * 365, 2),
            "annualised_estimated_meals": round(float(meals) / days * 365, 2),
        },
        "assumptions": ASSUMPTIONS,
        "model": {
            "engine": settings.forecast_engine,
            "forecaster": getattr(pipeline.forecaster, "model_name", "baseline-28d"),
            "interval": "80%",
            "cutoff": cutoff.isoformat(),
        },
    }
