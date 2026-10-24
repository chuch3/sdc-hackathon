from __future__ import annotations

import hashlib
import math
import statistics
import uuid
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from ..baseline import BaselineForecaster
from ..contracts import (
    Confidence,
    DailyForecast,
    DataQuality,
    ForecastContext,
    ForecastRequest,
    ForecastResult,
    Product,
    ReasonCode,
)
from ..forecasting import Forecaster
from ..policies import DemandPolicy, policies_for
from .config import MLConfig
from .features import build_product_history
from .registry import LocalModelRegistry

INTERVAL_Z = 1.2816


def _dedupe(codes: list[ReasonCode]) -> list[ReasonCode]:
    seen: set[ReasonCode] = set()
    result: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def _snapshot_id(
    request: ForecastRequest,
    product: Product,
    model_version: str,
) -> str:
    payload = (
        f"ml|{product.sku}|{request.as_of_date.isoformat()}|"
        f"{request.horizon_days}|{request.daypart}|{model_version}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class MLForecaster:
    def __init__(
        self,
        checkpoint_path: str | Path,
        baseline: Forecaster | None = None,
        min_valid_days: int = 14,
        low_coverage_days: int = 21,
        stale_after_days: int = 3,
        device: str = "cpu",
        model_name: str = "mlp-quantile",
        interval_z: float = INTERVAL_Z,
    ) -> None:
        if min_valid_days < 1:
            raise ValueError("min_valid_days must be positive")
        self.checkpoint_path = Path(checkpoint_path)
        self.baseline = baseline or BaselineForecaster()
        self.min_valid_days = min_valid_days
        self.low_coverage_days = low_coverage_days
        self.stale_after_days = stale_after_days
        self.device = device
        self.model_name = model_name
        self.interval_z = interval_z
        self._checkpoint = None
        self._load_error: str | None = None

    @classmethod
    def from_config(
        cls,
        config: MLConfig,
        checkpoint_path: str | Path | None = None,
        **kwargs,
    ) -> "MLForecaster":
        if checkpoint_path:
            path = Path(checkpoint_path)
        else:
            registry = LocalModelRegistry(
                config.registry_path,
                model_name=config.mlflow.model_name,
            )
            path = registry.resolve(config.mlflow.alias) or config.checkpoint_path
        return cls(path, **kwargs)

    def _ensure_checkpoint(self):
        if self._checkpoint is not None or self._load_error is not None:
            return self._checkpoint
        try:
            from .model import load_checkpoint

            self._checkpoint = load_checkpoint(
                self.checkpoint_path,
                device=self.device,
            )
        except Exception as error:
            self._load_error = f"{type(error).__name__}: {error}"
        return self._checkpoint

    def _fallback(
        self,
        request: ForecastRequest,
        context: ForecastContext,
        policy: DemandPolicy | None,
        explanation: str,
    ) -> ForecastResult:
        result = self.baseline.forecast(request, context, policy)
        codes = list(result.reason_codes)
        codes.append(ReasonCode.ML_FALLBACK_BASELINE)
        why = tuple(result.why) + (explanation,)
        return replace(
            result,
            reason_codes=tuple(_dedupe(codes)),
            why=why,
        )

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

        checkpoint = self._ensure_checkpoint()
        if checkpoint is None:
            return self._fallback(
                request,
                context,
                selected_policy,
                "ML checkpoint unavailable; using the rule-based baseline.",
            )
        if checkpoint.encoder.vocabulary.sku_index(product.sku) == 0:
            return self._fallback(
                request,
                context,
                selected_policy,
                "Product was not present when the ML model was trained; "
                "using the rule-based baseline.",
            )

        history = build_product_history(
            context,
            product.sku,
            request.as_of_date,
        )
        window_start = request.as_of_date - timedelta(days=27)
        window_dates = [
            window_start + timedelta(days=offset) for offset in range(28)
        ]
        valid_days = sum(
            1
            for day in window_dates
            if day in history.daily and day not in history.censored
        )
        censored_days = sum(
            1 for day in window_dates if day in history.censored
        )
        history_days = sum(1 for day in window_dates if day in history.daily)
        last_sale_date = history.last_sale_date
        stale = (
            last_sale_date is not None
            and last_sale_date
            < request.as_of_date - timedelta(days=self.stale_after_days)
        )
        cold_start = valid_days < self.min_valid_days
        if last_sale_date is None:
            return self._fallback(
                request,
                context,
                selected_policy,
                "No usable sales history; using the rule-based baseline.",
            )
        if stale:
            return self._fallback(
                request,
                context,
                selected_policy,
                "Sales history is stale; using the rule-based baseline.",
            )
        if cold_start:
            return self._fallback(
                request,
                context,
                selected_policy,
                "Not enough product history for the ML model; "
                "using the rule-based baseline.",
            )

        from .model import predict_dates

        target_dates = [
            request.as_of_date + timedelta(days=offset)
            for offset in range(1, request.horizon_days + 1)
        ]
        predictions = predict_dates(
            checkpoint,
            product,
            history,
            request.as_of_date,
            target_dates,
            context.overrides,
            device=self.device,
        )
        quantiles = checkpoint.model.quantiles
        low_index = 0
        high_index = len(quantiles) - 1
        middle_index = len(quantiles) // 2
        daypart_factor = selected_policy.daypart_share(
            product,
            request.daypart,
        )

        daily: list[DailyForecast] = []
        daily_stds: list[float] = []
        widths: list[float] = []
        for target_date, row in zip(target_dates, predictions):
            scaled = [value * daypart_factor for value in row]
            median = scaled[middle_index]
            low = scaled[low_index]
            high = scaled[high_index]
            upper_std = max(0.0, (high - median) / self.interval_z)
            lower_std = max(0.0, (median - low) / self.interval_z)
            day_std = (upper_std + lower_std) / 2.0
            daily_stds.append(day_std)
            widths.append((high - low) / (median + 1.0))
            daily.append(
                DailyForecast(
                    forecast_date=target_date,
                    quantity=median,
                    lower=max(0.0, low),
                    upper=high,
                    daypart=request.daypart,
                )
            )

        total_quantity = sum(item.quantity for item in daily)
        total_std = math.sqrt(sum(value**2 for value in daily_stds))
        total_lower = max(
            0.0,
            total_quantity - self.interval_z * total_std,
        )
        total_upper = total_quantity + self.interval_z * total_std
        error_std = statistics.fmean(daily_stds) if daily_stds else 0.0
        average_width = statistics.fmean(widths) if widths else 1.0
        censored_ratio = censored_days / 28.0
        if valid_days >= self.low_coverage_days and average_width <= 0.70:
            confidence = Confidence.HIGH
        elif valid_days >= self.min_valid_days and average_width <= 1.30:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW

        reason_codes = [ReasonCode.ML_FORECAST]
        if valid_days < self.low_coverage_days:
            reason_codes.append(ReasonCode.ML_LOW_COVERAGE)
        if censored_days > 0:
            reason_codes.append(ReasonCode.CENSORED_EXCLUDED)
        if censored_ratio > 0.10 or average_width > 1.30:
            reason_codes.append(ReasonCode.HIGH_VARIABILITY)
        holiday_applied = any(
            selected_policy.seasonal_factor(product, day, context.overrides)
            != 1.0
            for day in target_dates
        )
        if holiday_applied:
            reason_codes.append(ReasonCode.HOLIDAY_OVERRIDE)

        why = [
            f"Expected demand: {total_quantity:.0f} {product.unit} "
            f"over {request.horizon_days} days.",
            f"ML forecast ({checkpoint.model_version}) using "
            f"{valid_days} valid days of history and "
            f"{checkpoint.trained_at[:10] or 'unknown'} training data.",
            f"80% range: {total_lower:.0f}-{total_upper:.0f} {product.unit}; "
            f"confidence is {confidence.value}.",
        ]
        if valid_days < self.low_coverage_days:
            why.append(
                "History coverage is thin, so the ML forecast is flagged "
                "as low coverage."
            )
        if censored_days > 0:
            why.append(
                f"{censored_days} stockout-censored day(s) were excluded "
                "from the lags."
            )

        model_version = checkpoint.model_version
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
            model_version=model_version,
            reason_codes=tuple(_dedupe(reason_codes)),
            why=tuple(why),
            data_quality=DataQuality(
                window_days=28,
                history_days=history_days,
                valid_days=valid_days,
                censored_days=censored_days,
                last_sale_date=last_sale_date,
                cold_start=cold_start,
                stale=stale,
            ),
            forecast_run_id=request.forecast_run_id
            or f"fc-{uuid.uuid4().hex[:12]}",
            input_snapshot_id=request.input_snapshot_id
            or _snapshot_id(request, product, model_version),
            actionable=True,
        )
