from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping

import numpy as np

from .contracts import (
    CalendarOverride,
    Domain,
    InventoryPosition,
    Product,
    SalesObservation,
)

BAKERY_WEEKDAY_FACTORS = {
    0: 0.85,
    1: 0.85,
    2: 0.90,
    3: 0.95,
    4: 1.15,
    5: 1.30,
    6: 1.05,
}
BAKERY_DAYPART_SHARES = {
    "morning": 0.45,
    "midday": 0.30,
    "afternoon": 0.18,
    "evening": 0.07,
}
BASE_DEMAND = {
    "sourdough": 42.0,
    "baguette": 58.0,
    "wholemeal": 28.0,
    "croissant": 36.0,
    "milk": 80.0,
    "yogurt": 50.0,
    "apples": 65.0,
    "chicken": 24.0,
}
STOCKOUT_DAYS = {
    "sourdough": {12, 31},
    "milk": {8, 27},
    "croissant": {18},
    "chicken": {5},
}


@dataclass(frozen=True)
class SyntheticDataset:
    as_of_date: date
    products: tuple[Product, ...]
    observations: tuple[SalesObservation, ...]
    ground_truth: tuple[SalesObservation, ...]
    inventory: tuple[InventoryPosition, ...]
    overrides: tuple[CalendarOverride, ...]


def build_sample_products() -> tuple[Product, ...]:
    return (
        Product(
            sku="sourdough",
            name="Sourdough loaf",
            category="bakery",
            domain=Domain.BAKERY,
            unit="loaf",
            shelf_life_days=2,
            lead_time_days=1,
            review_period_days=1,
            moq=5,
            case_size=5,
            safety_stock_days=0.5,
            service_level=0.95,
            weekday_factors=BAKERY_WEEKDAY_FACTORS,
            daypart_shares=BAKERY_DAYPART_SHARES,
            near_expiry_threshold_days=1,
        ),
        Product(
            sku="baguette",
            name="Baguette",
            category="bakery",
            domain=Domain.BAKERY,
            unit="loaf",
            shelf_life_days=1,
            lead_time_days=1,
            review_period_days=1,
            moq=10,
            case_size=10,
            safety_stock_days=0.25,
            service_level=0.95,
            weekday_factors=BAKERY_WEEKDAY_FACTORS,
            daypart_shares=BAKERY_DAYPART_SHARES,
            near_expiry_threshold_days=1,
        ),
        Product(
            sku="wholemeal",
            name="Wholemeal loaf",
            category="bakery",
            domain=Domain.BAKERY,
            unit="loaf",
            shelf_life_days=2,
            lead_time_days=1,
            review_period_days=1,
            moq=5,
            case_size=5,
            safety_stock_days=0.5,
            service_level=0.95,
            weekday_factors=BAKERY_WEEKDAY_FACTORS,
            daypart_shares=BAKERY_DAYPART_SHARES,
            near_expiry_threshold_days=1,
        ),
        Product(
            sku="croissant",
            name="Butter croissant",
            category="bakery",
            domain=Domain.BAKERY,
            unit="piece",
            shelf_life_days=2,
            lead_time_days=1,
            review_period_days=1,
            moq=6,
            case_size=6,
            safety_stock_days=0.5,
            service_level=0.95,
            weekday_factors=BAKERY_WEEKDAY_FACTORS,
            daypart_shares=BAKERY_DAYPART_SHARES,
            near_expiry_threshold_days=1,
        ),
        Product(
            sku="milk",
            name="Whole milk 1L",
            category="dairy",
            domain=Domain.GENERIC,
            unit="bottle",
            shelf_life_days=7,
            lead_time_days=2,
            review_period_days=1,
            moq=12,
            case_size=12,
            safety_stock_days=1.0,
            service_level=0.95,
            near_expiry_threshold_days=3,
        ),
        Product(
            sku="yogurt",
            name="Natural yogurt 500g",
            category="dairy",
            domain=Domain.GENERIC,
            unit="tub",
            shelf_life_days=10,
            lead_time_days=2,
            review_period_days=1,
            moq=12,
            case_size=12,
            safety_stock_days=1.0,
            service_level=0.95,
            near_expiry_threshold_days=3,
        ),
        Product(
            sku="apples",
            name="Apples",
            category="produce",
            domain=Domain.GENERIC,
            unit="kg",
            shelf_life_days=5,
            lead_time_days=2,
            review_period_days=1,
            moq=10,
            case_size=10,
            safety_stock_days=1.0,
            service_level=0.95,
            near_expiry_threshold_days=2,
        ),
        Product(
            sku="chicken",
            name="Chicken breast",
            category="meat",
            domain=Domain.GENERIC,
            unit="kg",
            shelf_life_days=2,
            lead_time_days=1,
            review_period_days=1,
            moq=5,
            case_size=5,
            safety_stock_days=0.5,
            service_level=0.95,
            near_expiry_threshold_days=1,
        ),
    )


def _split_total(total: int, shares: Mapping[str, float]) -> dict[str, int]:
    raw = {name: total * share for name, share in shares.items()}
    split = {name: int(math.floor(value)) for name, value in raw.items()}
    remaining = total - sum(split.values())
    order = sorted(raw, key=lambda name: raw[name] - split[name], reverse=True)
    for name in order[:remaining]:
        split[name] += 1
    return split


def _override_factor(
    overrides: tuple[CalendarOverride, ...],
    product: Product,
    day: date,
) -> float:
    factors = [
        override.multiplier
        for override in overrides
        if override.business_date == day
        and override.product_sku in (None, product.sku)
    ]
    return math.prod(factors) if factors else 1.0


def generate_synthetic_dataset(
    seed: int = 42,
    as_of_date: date | None = None,
    days: int = 56,
) -> SyntheticDataset:
    if days < 14:
        raise ValueError("days must be at least 14")
    as_of = as_of_date or date.today()
    start = as_of - timedelta(days=days - 1)
    rng = np.random.default_rng(seed)
    products = build_sample_products()
    overrides = (
        CalendarOverride(
            business_date=start + timedelta(days=20),
            multiplier=1.40,
            product_sku="sourdough",
            kind="holiday",
        ),
        CalendarOverride(
            business_date=start + timedelta(days=35),
            multiplier=1.30,
            product_sku="milk",
            kind="promo",
        ),
    )

    observations: list[SalesObservation] = []
    ground_truth: list[SalesObservation] = []

    for product in products:
        base = BASE_DEMAND[product.sku]
        for day_index in range(days):
            business_date = start + timedelta(days=day_index)
            weekday = product.weekday_factors.get(business_date.weekday(), 1.0)
            seasonal = (
                1.0 + 0.08 * math.sin(2.0 * math.pi * day_index / 28.0)
                if product.domain is Domain.BAKERY
                else 1.0
            )
            override = _override_factor(overrides, product, business_date)
            mean = base * weekday * seasonal * override
            noise = rng.normal(loc=0.0, scale=max(1.0, mean * 0.15))
            true_demand = max(0, int(round(mean + noise)))
            is_stockout = (
                day_index in STOCKOUT_DAYS.get(product.sku, set())
                and true_demand > 0
            )
            sold = (
                max(1, int(round(true_demand * 0.50)))
                if is_stockout
                else true_demand
            )

            if product.domain is Domain.BAKERY:
                truth_split = _split_total(true_demand, product.daypart_shares)
                sold_split = _split_total(sold, product.daypart_shares)
                for daypart in product.daypart_shares:
                    ground_truth.append(
                        SalesObservation(
                            product_sku=product.sku,
                            business_date=business_date,
                            quantity=float(truth_split[daypart]),
                            daypart=daypart,
                            is_stockout_censored=False,
                        )
                    )
                    observations.append(
                        SalesObservation(
                            product_sku=product.sku,
                            business_date=business_date,
                            quantity=float(sold_split[daypart]),
                            daypart=daypart,
                            is_stockout_censored=is_stockout,
                        )
                    )
            else:
                ground_truth.append(
                    SalesObservation(
                        product_sku=product.sku,
                        business_date=business_date,
                        quantity=float(true_demand),
                        is_stockout_censored=False,
                    )
                )
                observations.append(
                    SalesObservation(
                        product_sku=product.sku,
                        business_date=business_date,
                        quantity=float(sold),
                        is_stockout_censored=is_stockout,
                    )
                )

    inventory = (
        InventoryPosition("sourdough", 25, 0, 2),
        InventoryPosition("baguette", 15, 0, 1),
        InventoryPosition("wholemeal", 30, 0, 2),
        InventoryPosition("croissant", 55, 0, 1),
        InventoryPosition("milk", 20, 0, 7),
        InventoryPosition("yogurt", 300, 0, 10),
        InventoryPosition("apples", 300, 0, 5),
        InventoryPosition("chicken", 8, 0, 2),
    )

    return SyntheticDataset(
        as_of_date=as_of,
        products=products,
        observations=tuple(observations),
        ground_truth=tuple(ground_truth),
        inventory=inventory,
        overrides=overrides,
    )
