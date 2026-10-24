from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from .baseline import BaselineForecaster
from .contracts import (
    Action,
    ForecastContext,
    ForecastRequest,
    Recommendation,
)
from .forecasting import Forecaster
from .policies import policies_for
from .reorder import ReorderService
from .repository import ForecastRepository


def _priority(recommendation: Recommendation) -> tuple[int, str]:
    order = {
        Action.MARKDOWN: 0,
        Action.BUY: 1,
        Action.BAKE: 1,
        Action.HOLD: 2,
    }
    return (order.get(recommendation.action, 3), recommendation.product_sku)


@dataclass
class ForecastPipeline:
    repository: ForecastRepository
    forecaster: Forecaster = field(default_factory=BaselineForecaster)
    reorder: ReorderService = field(default_factory=ReorderService)

    def build_context(self, as_of: date | None = None) -> ForecastContext:
        products = {product.sku: product for product in self.repository.products()}
        history = [
            observation
            for observation in self.repository.sales_history()
            if as_of is None or observation.business_date <= as_of
        ]
        return ForecastContext(
            products=products,
            sales_history=tuple(history),
            overrides=tuple(self.repository.overrides()),
        )

    def recommend_one(
        self,
        product_sku: str,
        as_of: date,
        context: ForecastContext | None = None,
    ) -> Recommendation:
        selected_context = context or self.build_context(as_of)
        product = selected_context.products.get(product_sku)
        if product is None:
            raise KeyError(f"unknown product: {product_sku}")
        position = next(
            (
                item
                for item in self.repository.inventory()
                if item.product_sku == product_sku
            ),
            None,
        )
        if position is None:
            raise KeyError(f"missing inventory position for: {product_sku}")

        policies = policies_for(product)
        run_id = uuid.uuid4().hex[:12]
        horizon = product.lead_time_days + product.review_period_days
        forecast = self.forecaster.forecast(
            ForecastRequest(
                product_sku=product.sku,
                as_of_date=as_of,
                horizon_days=max(1, horizon),
                forecast_run_id=run_id,
            ),
            selected_context,
            policies.demand,
        )
        shelf_horizon = min(position.remaining_shelf_life_days, horizon)
        shelf_forecast = None
        if shelf_horizon >= 1:
            shelf_forecast = self.forecaster.forecast(
                ForecastRequest(
                    product_sku=product.sku,
                    as_of_date=as_of,
                    horizon_days=shelf_horizon,
                    forecast_run_id=run_id,
                ),
                selected_context,
                policies.demand,
            )
        return self.reorder.recommend(
            product=product,
            position=position,
            forecast=forecast,
            policies=policies,
            shelf_forecast=shelf_forecast,
        )

    def recommend_all(
        self,
        as_of: date,
        product_skus: Iterable[str] | None = None,
    ) -> list[Recommendation]:
        context = self.build_context(as_of)
        skus = (
            list(product_skus)
            if product_skus is not None
            else [item.product_sku for item in self.repository.inventory()]
        )
        recommendations = [
            self.recommend_one(sku, as_of, context)
            for sku in skus
            if sku in context.products
        ]
        return sorted(recommendations, key=_priority)
