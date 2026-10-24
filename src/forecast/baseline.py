from __future__ import annotations

import hashlib
import math
import statistics
import uuid
from collections import defaultdict
from datetime import date, timedelta

from .contracts import (
    Confidence,
    DailyForecast,
    DataQuality,
    ForecastContext,
    ForecastRequest,
    ForecastResult,
    Product,
    ReasonCode,
)
from .policies import DemandPolicy, policies_for


def _dedupe(codes: list[ReasonCode]) -> list[ReasonCode]:
    seen: set[ReasonCode] = set()
    result: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def _category_daily_average(
    context: ForecastContext,
    category: str,
    start: date,
    as_of: date,
) -> float:
    skus = {
        product.sku
        for product in context.products.values()
        if product.category == category
    }
    if not skus:
        return 0.0
    daily: dict[date, float] = defaultdict(float)
    active_skus: set[str] = set()
    for observation in context.sales_history:
        if (
            observation.product_sku in skus
            and start <= observation.business_date <= as_of
            and not observation.is_stockout_censored
        ):
            daily[observation.business_date] += observation.quantity
            active_skus.add(observation.product_sku)
    if not daily or not active_skus:
        return 0.0
    return sum(daily.values()) / (len(daily) * len(active_skus))


def _snapshot_id(request: ForecastRequest, product: Product) -> str:
    payload = (
        f"{product.sku}|{request.as_of_date.isoformat()}|"
        f"{request.horizon_days}|{request.daypart}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class BaselineForecaster:
    def __init__(
        self,
        window_days: int = 28,
        min_valid_days: int = 14,
        interval_z: float = 1.2816,
        model_name: str = "baseline-28d",
        model_version: str = "1.0.0",
    ) -> None:
        if window_days < 1:
            raise ValueError("window_days must be positive")
        if min_valid_days < 1:
            raise ValueError("min_valid_days must be positive")
        self.window_days = window_days
        self.min_valid_days = min_valid_days
        self.interval_z = interval_z
        self.model_name = model_name
        self.model_version = model_version

    def forecast(
        self,
        request: ForecastRequest,
        context: ForecastContext,
        policy: DemandPolicy | None = None,
    ) -> ForecastResult:
        if request.horizon_days < 1:
            raise ValueError("horizon_days must be positive")
        product = context.products.get(request.product_sku)
        if product is None:
            raise KeyError(f"unknown product: {request.product_sku}")
        selected_policy = policy or policies_for(product).demand

        start = request.as_of_date - timedelta(days=self.window_days - 1)
        by_date: dict[date, float] = defaultdict(float)
        censored_dates: set[date] = set()
        for observation in context.sales_history:
            if (
                observation.product_sku == product.sku
                and start <= observation.business_date <= request.as_of_date
            ):
                by_date[observation.business_date] += observation.quantity
                if observation.is_stockout_censored:
                    censored_dates.add(observation.business_date)

        dates = [start + timedelta(days=offset) for offset in range(self.window_days)]
        valid_values = [
            by_date[day]
            for day in dates
            if day in by_date and day not in censored_dates
        ]
        censored_days = len([day for day in dates if day in censored_dates])
        history_days = len(by_date)
        last_sale_date = max(by_date) if by_date else None
        stale = (
            last_sale_date is not None
            and last_sale_date < request.as_of_date - timedelta(days=3)
        )

        cold_start = False
        no_history = False
        if len(valid_values) >= self.min_valid_days:
            base_mean = statistics.fmean(valid_values)
        else:
            category_mean = _category_daily_average(
                context, product.category, start, request.as_of_date
            )
            if category_mean > 0:
                base_mean = category_mean
                cold_start = True
            else:
                base_mean = 0.0
                no_history = True

        if len(valid_values) >= 2:
            error_std = statistics.pstdev(valid_values)
        elif base_mean > 0:
            error_std = base_mean * 0.30
        else:
            error_std = 0.0

        coefficient_of_variation = error_std / base_mean if base_mean > 0 else 1.0
        censored_ratio = censored_days / self.window_days
        if no_history or stale:
            confidence = Confidence.LOW
        elif cold_start:
            confidence = Confidence.LOW
        elif (
            len(valid_values) >= 21
            and coefficient_of_variation <= 0.35
            and censored_ratio <= 0.10
        ):
            confidence = Confidence.HIGH
        elif len(valid_values) >= self.min_valid_days and coefficient_of_variation <= 0.60:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        daily: list[DailyForecast] = []
        daily_stds: list[float] = []
        reason_codes: list[ReasonCode] = []
        if not cold_start and not no_history:
            reason_codes.append(ReasonCode.BASELINE_28D)
        if cold_start:
            reason_codes.append(ReasonCode.COLD_START)
            reason_codes.append(ReasonCode.LOW_HISTORY)
        if no_history:
            reason_codes.append(ReasonCode.NO_HISTORY)
        if censored_days > 0:
            reason_codes.append(ReasonCode.CENSORED_EXCLUDED)
        if coefficient_of_variation > 0.60:
            reason_codes.append(ReasonCode.HIGH_VARIABILITY)
        if stale:
            reason_codes.append(ReasonCode.STALE_DATA)

        holiday_applied = False
        weekday_applied = False
        daypart_applied = False

        for offset in range(1, request.horizon_days + 1):
            forecast_date = request.as_of_date + timedelta(days=offset)
            weekday_factor = selected_policy.weekday_factor(product, forecast_date)
            seasonal_factor = selected_policy.seasonal_factor(
                product, forecast_date, context.overrides
            )
            daypart_factor = selected_policy.daypart_share(product, request.daypart)
            factor = weekday_factor * seasonal_factor * daypart_factor
            quantity = base_mean * factor
            day_std = error_std * factor
            daily_stds.append(day_std)
            if weekday_factor != 1.0:
                weekday_applied = True
            if seasonal_factor != 1.0:
                holiday_applied = True
            if daypart_factor != 1.0:
                daypart_applied = True
            daily.append(
                DailyForecast(
                    forecast_date=forecast_date,
                    quantity=quantity,
                    lower=max(0.0, quantity - self.interval_z * day_std),
                    upper=quantity + self.interval_z * day_std,
                    daypart=request.daypart,
                )
            )

        if weekday_applied:
            reason_codes.append(ReasonCode.WEEKDAY_FACTOR)
        if holiday_applied:
            reason_codes.append(ReasonCode.HOLIDAY_OVERRIDE)
        if daypart_applied:
            reason_codes.append(ReasonCode.DAYPART_SHARE)

        total_quantity = sum(item.quantity for item in daily)
        total_std = math.sqrt(sum(value**2 for value in daily_stds))
        total_lower = max(0.0, total_quantity - self.interval_z * total_std)
        total_upper = total_quantity + self.interval_z * total_std

        if no_history:
            why = [
                "No usable sales history is available yet.",
                "No stock recommendation is possible until sales data exists.",
                "Confidence is low.",
            ]
        elif cold_start:
            why = [
                f"Expected demand: {total_quantity:.0f} {product.unit} over {request.horizon_days} days.",
                f"Not enough product history; using the {product.category} category average.",
                "Confidence is low because this product is new or sparse.",
            ]
        else:
            why = [
                f"Expected demand: {total_quantity:.0f} {product.unit} over {request.horizon_days} days.",
                f"Based on {len(valid_values)} valid days of sales; "
                f"{censored_days} stockout days excluded.",
                f"Confidence is {confidence.value} "
                f"with variability {coefficient_of_variation:.0%}.",
            ]

        actionable = not no_history and not stale
        return ForecastResult(
            product_sku=product.sku,
            as_of_date=request.as_of_date,
            horizon_days=request.horizon_days,
            daily=tuple(daily),
            total_quantity=total_quantity,
            total_lower=total_lower,
            total_upper=total_upper,
            error_std=error_std,
            confidence=confidence,
            model_name=self.model_name,
            model_version=self.model_version,
            reason_codes=tuple(_dedupe(reason_codes)),
            why=tuple(why),
            data_quality=DataQuality(
                window_days=self.window_days,
                history_days=history_days,
                valid_days=len(valid_values),
                censored_days=censored_days,
                last_sale_date=last_sale_date,
                cold_start=cold_start,
                stale=stale,
            ),
            forecast_run_id=request.forecast_run_id or f"fc-{uuid.uuid4().hex[:12]}",
            input_snapshot_id=request.input_snapshot_id or _snapshot_id(request, product),
            actionable=actionable,
        )
