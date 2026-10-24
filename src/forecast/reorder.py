from __future__ import annotations

import math
from statistics import NormalDist

from .contracts import (
    Action,
    ForecastResult,
    InventoryPosition,
    Product,
    ReasonCode,
    Recommendation,
)
from .policies import DecisionPolicies


def _lot_size(product: Product) -> int:
    return max(product.moq, product.case_size, 1)


def _expiry_risk(product: Product, position: InventoryPosition) -> str:
    days = position.remaining_shelf_life_days
    threshold = product.near_expiry_threshold_days
    if days < 0:
        return "expired"
    if days <= threshold:
        return "critical"
    if days <= threshold * 2:
        return "warning"
    return "healthy"


def _service_z(service_level: float) -> float:
    clamped = min(max(service_level, 0.50), 0.999)
    return NormalDist().inv_cdf(clamped)


class ReorderService:
    def __init__(self, interval_z: float = 1.2816) -> None:
        self.interval_z = interval_z

    def recommend(
        self,
        product: Product,
        position: InventoryPosition,
        forecast: ForecastResult,
        policies: DecisionPolicies,
        shelf_forecast: ForecastResult | None = None,
    ) -> Recommendation:
        horizon = forecast.horizon_days
        error_std = (
            position.forecast_error
            if position.forecast_error is not None
            else forecast.error_std
        )
        z = _service_z(product.service_level)
        safety_stock = z * error_std * math.sqrt(max(horizon, 1))
        reorder_point = forecast.total_quantity + safety_stock
        raw_order = reorder_point - position.saleable_on_hand - position.on_order
        shelf_total = (
            shelf_forecast.total_quantity
            if shelf_forecast is not None
            else forecast.total_quantity
        )
        fresh_cap = (
            shelf_total + safety_stock - position.saleable_on_hand
        )
        surplus = position.saleable_on_hand - shelf_total
        calculation = {
            "saleable_on_hand": position.saleable_on_hand,
            "on_order": position.on_order,
            "forecast_total": forecast.total_quantity,
            "forecast_error_std": error_std,
            "safety_stock": safety_stock,
            "reorder_point": reorder_point,
            "raw_order": raw_order,
            "fresh_cap": fresh_cap,
            "surplus": surplus,
            "service_level": product.service_level,
            "service_z": z,
        }
        expiry_risk = _expiry_risk(product, position)

        if not forecast.actionable:
            return Recommendation(
                product_sku=product.sku,
                product_name=product.name,
                action=Action.HOLD,
                quantity=0.0,
                rationale=(
                    "Forecast is blocked because demand data is missing or stale.\n"
                    "No purchase, bake, or markdown is recommended.\n"
                    "Resolve the data quality issue before approving any action."
                ),
                why=tuple(forecast.why),
                confidence=forecast.confidence,
                reason_codes=tuple(forecast.reason_codes)
                + (ReasonCode.BLOCKED_DATA_QUALITY,),
                expiry_risk=expiry_risk,
                forecast_horizon_days=horizon,
                calculation=calculation,
                forecast=forecast,
                shelf_forecast=shelf_forecast,
                forecast_run_id=forecast.forecast_run_id,
                input_snapshot_id=forecast.input_snapshot_id,
            )

        if (
            shelf_forecast is not None
            and policies.advice.should_markdown(
                product, position, shelf_forecast.total_quantity
            )
            and surplus > 0
        ):
            markdown_quantity = max(1, math.floor(surplus))
            return Recommendation(
                product_sku=product.sku,
                product_name=product.name,
                action=Action.MARKDOWN,
                quantity=float(markdown_quantity),
                rationale=(
                    f"{position.saleable_on_hand:.0f} {product.unit} are saleable "
                    f"with {position.remaining_shelf_life_days} day(s) of shelf life left.\n"
                    f"Expected sales before expiry are only {shelf_total:.0f} {product.unit}.\n"
                    f"Mark down {markdown_quantity} {product.unit} to sell before expiry."
                ),
                why=(
                    f"Surplus at risk: {surplus:.0f} {product.unit}.",
                    "Expected sales before expiry are lower than on-hand stock.",
                    "Markdown is recommended before considering waste or donation.",
                ),
                confidence=forecast.confidence,
                reason_codes=(ReasonCode.NEAR_EXPIRY_SURPLUS,),
                expiry_risk=expiry_risk,
                forecast_horizon_days=horizon,
                calculation=calculation,
                forecast=forecast,
                shelf_forecast=shelf_forecast,
                forecast_run_id=forecast.forecast_run_id,
                input_snapshot_id=forecast.input_snapshot_id,
            )

        if raw_order <= 0:
            return Recommendation(
                product_sku=product.sku,
                product_name=product.name,
                action=Action.HOLD,
                quantity=0.0,
                rationale=(
                    f"Expected demand over {horizon} days is "
                    f"{forecast.total_quantity:.0f} {product.unit}.\n"
                    f"Saleable on hand is {position.saleable_on_hand:.0f} "
                    f"and on order is {position.on_order:.0f}.\n"
                    "Stock already covers the reorder point, so hold."
                ),
                why=(
                    "No replenishment is needed.",
                    "On-hand and on-order stock cover expected demand plus safety stock.",
                    "Default action is no action until stock changes.",
                ),
                confidence=forecast.confidence,
                reason_codes=(ReasonCode.NO_REORDER,),
                expiry_risk=expiry_risk,
                forecast_horizon_days=horizon,
                calculation=calculation,
                forecast=forecast,
                shelf_forecast=shelf_forecast,
                forecast_run_id=forecast.forecast_run_id,
                input_snapshot_id=forecast.input_snapshot_id,
            )

        recommended = max(0.0, min(raw_order, fresh_cap))
        if recommended <= 0:
            return Recommendation(
                product_sku=product.sku,
                product_name=product.name,
                action=Action.HOLD,
                quantity=0.0,
                rationale=(
                    f"Expected demand over {horizon} days is "
                    f"{forecast.total_quantity:.0f} {product.unit}.\n"
                    f"Shelf life allows only {shelf_total:.0f} {product.unit} to sell.\n"
                    "Do not replenish more than can sell before expiry."
                ),
                why=(
                    "Shelf-life cap blocks a fresh order.",
                    "On-hand stock already covers demand before expiry.",
                    "Review markdown or donation options instead.",
                ),
                confidence=forecast.confidence,
                reason_codes=(ReasonCode.SHELF_LIFE_CAP, ReasonCode.NO_REORDER),
                expiry_risk=expiry_risk,
                forecast_horizon_days=horizon,
                calculation=calculation,
                forecast=forecast,
                shelf_forecast=shelf_forecast,
                forecast_run_id=forecast.forecast_run_id,
                input_snapshot_id=forecast.input_snapshot_id,
            )

        lot = _lot_size(product)
        rounded = math.ceil(recommended / lot) * lot
        if rounded > fresh_cap:
            rounded = math.floor(fresh_cap / lot) * lot
        if rounded <= 0:
            return Recommendation(
                product_sku=product.sku,
                product_name=product.name,
                action=Action.HOLD,
                quantity=0.0,
                rationale=(
                    f"Expected demand over {horizon} days is "
                    f"{forecast.total_quantity:.0f} {product.unit}.\n"
                    "Rounding to the supplier lot size would exceed the shelf-life cap.\n"
                    "Review markdown or donation options before ordering."
                ),
                why=(
                    "The fresh-order cap leaves no full lot available.",
                    "Ordering a full lot would create avoidable expiry risk.",
                    "Default action is hold until stock changes.",
                ),
                confidence=forecast.confidence,
                reason_codes=(ReasonCode.SHELF_LIFE_CAP, ReasonCode.NO_REORDER),
                expiry_risk=expiry_risk,
                forecast_horizon_days=horizon,
                calculation=calculation,
                forecast=forecast,
                shelf_forecast=shelf_forecast,
                forecast_run_id=forecast.forecast_run_id,
                input_snapshot_id=forecast.input_snapshot_id,
            )
        action = policies.planning.replenishment_action()
        reasons = [ReasonCode.REORDER_POINT]
        if raw_order > fresh_cap:
            reasons.append(ReasonCode.SHELF_LIFE_CAP)
        if rounded != recommended:
            reasons.append(ReasonCode.MOQ_ROUNDED)
        verb = "bake" if action is Action.BAKE else "buy"
        return Recommendation(
            product_sku=product.sku,
            product_name=product.name,
            action=action,
            quantity=float(rounded),
            rationale=(
                f"Expected demand over {horizon} days is "
                f"{forecast.total_quantity:.0f} {product.unit}.\n"
                f"Saleable on hand is {position.saleable_on_hand:.0f}; "
                f"lead time is {product.lead_time_days} day(s).\n"
                f"{verb.capitalize()} {rounded} {product.unit} "
                f"(reorder point {reorder_point:.0f})."
            ),
            why=(
                f"Reorder point {reorder_point:.0f} exceeds available stock.",
                f"Fresh-order cap is {fresh_cap:.0f} {product.unit} after shelf life.",
                f"Order is rounded up to a lot size of {lot}.",
            ),
            confidence=forecast.confidence,
            reason_codes=tuple(reasons),
            expiry_risk=expiry_risk,
            forecast_horizon_days=horizon,
            calculation=calculation,
            forecast=forecast,
            shelf_forecast=shelf_forecast,
            forecast_run_id=forecast.forecast_run_id,
            input_snapshot_id=forecast.input_snapshot_id,
        )
