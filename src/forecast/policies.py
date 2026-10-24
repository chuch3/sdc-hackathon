from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Protocol, Sequence

from .contracts import Action, CalendarOverride, Domain, InventoryPosition, Product


class DemandPolicy(Protocol):
    def weekday_factor(self, product: Product, day: date) -> float: ...

    def daypart_share(self, product: Product, daypart: str | None) -> float: ...

    def seasonal_factor(
        self,
        product: Product,
        day: date,
        overrides: Sequence[CalendarOverride],
    ) -> float: ...


class PlanningPolicy(Protocol):
    def replenishment_action(self) -> Action: ...


class AdvicePolicy(Protocol):
    def should_markdown(
        self,
        product: Product,
        position: InventoryPosition,
        forecast_before_expiry: float,
    ) -> bool: ...


class BaseDemandPolicy:
    def seasonal_factor(
        self,
        product: Product,
        day: date,
        overrides: Sequence[CalendarOverride],
    ) -> float:
        factors = [
            override.multiplier
            for override in overrides
            if override.business_date == day
            and override.product_sku in (None, product.sku)
        ]
        return math.prod(factors) if factors else 1.0


class GenericDemandPolicy(BaseDemandPolicy):
    def weekday_factor(self, product: Product, day: date) -> float:
        return 1.0

    def daypart_share(self, product: Product, daypart: str | None) -> float:
        return 1.0


class BakeryDemandPolicy(BaseDemandPolicy):
    def weekday_factor(self, product: Product, day: date) -> float:
        return product.weekday_factors.get(day.weekday(), 1.0)

    def daypart_share(self, product: Product, daypart: str | None) -> float:
        if daypart is None:
            return 1.0
        return product.daypart_shares.get(daypart, 1.0)


class GenericPlanningPolicy:
    def replenishment_action(self) -> Action:
        return Action.BUY


class BakeryPlanningPolicy:
    def replenishment_action(self) -> Action:
        return Action.BAKE


class ThresholdAdvicePolicy:
    def should_markdown(
        self,
        product: Product,
        position: InventoryPosition,
        forecast_before_expiry: float,
    ) -> bool:
        if position.remaining_shelf_life_days <= 0:
            return False
        return (
            position.remaining_shelf_life_days <= product.near_expiry_threshold_days
            and position.saleable_on_hand > forecast_before_expiry
        )


@dataclass(frozen=True)
class DecisionPolicies:
    demand: DemandPolicy
    planning: PlanningPolicy
    advice: AdvicePolicy


def policies_for(product: Product) -> DecisionPolicies:
    if product.domain is Domain.BAKERY:
        return DecisionPolicies(
            demand=BakeryDemandPolicy(),
            planning=BakeryPlanningPolicy(),
            advice=ThresholdAdvicePolicy(),
        )
    return DecisionPolicies(
        demand=GenericDemandPolicy(),
        planning=GenericPlanningPolicy(),
        advice=ThresholdAdvicePolicy(),
    )
