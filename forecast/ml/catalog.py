from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta

import numpy as np

from ..contracts import (
    CalendarOverride,
    Domain,
    InventoryPosition,
    Product,
    SalesObservation,
)
from ..synthetic import BASE_DEMAND, SyntheticDataset, build_sample_products

HOLIDAY_MULTIPLIER = 1.28
PROMO_MULTIPLIER = 1.35
STOCKOUT_RATE = 0.012


def _split_total(total: int, shares: dict[str, float]) -> dict[str, int]:
    raw = {name: total * share for name, share in shares.items()}
    split = {name: int(math.floor(value)) for name, value in raw.items()}
    remaining = total - sum(split.values())
    order = sorted(raw, key=lambda name: raw[name] - split[name], reverse=True)
    for name in order[:remaining]:
        split[name] += 1
    return split


def expand_products(count: int, seed: int = 42) -> tuple[Product, ...]:
    base_products = build_sample_products()
    if count <= len(base_products):
        return base_products[:count]
    rng = np.random.default_rng(seed + 1)
    products: list[Product] = list(base_products)
    for index in range(len(base_products), count):
        base = base_products[index % len(base_products)]
        variant = index // len(base_products) + 1
        scale = 0.65 + 0.11 * variant
        jitter = {
            weekday: factor * float(rng.uniform(0.94, 1.06))
            for weekday, factor in base.weekday_factors.items()
        }
        products.append(
            replace(
                base,
                sku=f"{base.sku}-{variant}",
                name=f"{base.name} #{variant}",
                moq=max(1, int(round(base.moq * scale))),
                case_size=max(1, int(round(base.case_size * scale))),
                weekday_factors=jitter,
            )
        )
    return tuple(products)


def _scale_for(product: Product) -> float:
    if "-" not in product.sku:
        return 1.0
    tail = product.sku.rsplit("-", 1)[-1]
    try:
        variant = int(tail)
    except ValueError:
        return 1.0
    return 0.65 + 0.11 * variant


def build_training_dataset(
    seed: int = 42,
    as_of_date: date | None = None,
    days: int = 730,
    products: int = 60,
) -> SyntheticDataset:
    if days < 90:
        raise ValueError("training data needs at least 90 days")
    as_of = as_of_date or date.today()
    start = as_of - timedelta(days=days - 1)
    rng = np.random.default_rng(seed)
    expanded = expand_products(products, seed=seed)

    holiday_offsets = sorted(
        {
            int(round(days * fraction))
            for fraction in (0.08, 0.21, 0.34, 0.47, 0.60, 0.73, 0.86, 0.97)
        }
    )
    overrides: list[CalendarOverride] = [
        CalendarOverride(
            business_date=start + timedelta(days=offset),
            multiplier=HOLIDAY_MULTIPLIER,
            product_sku=None,
            kind="holiday",
        )
        for offset in holiday_offsets
    ]
    for product in expanded:
        picks = sorted(
            int(value)
            for value in rng.choice(
                np.arange(10, days - 10),
                size=3,
                replace=False,
            )
        )
        for offset in picks:
            overrides.append(
                CalendarOverride(
                    business_date=start + timedelta(days=offset),
                    multiplier=PROMO_MULTIPLIER,
                    product_sku=product.sku,
                    kind="promo",
                )
            )

    override_index: dict[tuple[date, str | None], float] = {}
    for override in overrides:
        override_index[(override.business_date, override.product_sku)] = (
            override_index.get((override.business_date, override.product_sku), 1.0)
            * override.multiplier
        )

    observations: list[SalesObservation] = []
    ground_truth: list[SalesObservation] = []
    for product_index, product in enumerate(expanded):
        base = BASE_DEMAND[product.sku.split("-")[0]]
        scale = _scale_for(product)
        phase = float(rng.uniform(0.0, 2.0 * math.pi))
        generated: list[tuple[date, int]] = []
        for day_index in range(days):
            business_date = start + timedelta(days=day_index)
            weekday = product.weekday_factors.get(business_date.weekday(), 1.0)
            annual = 1.0 + 0.12 * math.sin(
                2.0 * math.pi * day_index / 365.0 + phase
            )
            trend = 1.0 + 0.00015 * day_index
            holiday = override_index.get((business_date, None), 1.0)
            promo = override_index.get((business_date, product.sku), 1.0)
            mean = base * scale * weekday * annual * trend * holiday * promo
            noise = rng.normal(loc=0.0, scale=max(1.0, mean * 0.16))
            true_demand = max(0, int(round(mean + noise)))
            generated.append((business_date, true_demand))

        for business_date, true_demand in generated:
            stockout = bool(rng.random() < STOCKOUT_RATE and true_demand > 0)
            sold = (
                max(1, int(round(true_demand * rng.uniform(0.35, 0.65))))
                if stockout
                else true_demand
            )
            if product.domain is Domain.BAKERY:
                truth_split = _split_total(
                    true_demand, dict(product.daypart_shares)
                )
                sold_split = _split_total(sold, dict(product.daypart_shares))
                for daypart in product.daypart_shares:
                    ground_truth.append(
                        SalesObservation(
                            product_sku=product.sku,
                            business_date=business_date,
                            quantity=float(truth_split[daypart]),
                            daypart=daypart,
                        )
                    )
                    observations.append(
                        SalesObservation(
                            product_sku=product.sku,
                            business_date=business_date,
                            quantity=float(sold_split[daypart]),
                            daypart=daypart,
                            is_stockout_censored=stockout,
                        )
                    )
            else:
                ground_truth.append(
                    SalesObservation(
                        product_sku=product.sku,
                        business_date=business_date,
                        quantity=float(true_demand),
                    )
                )
                observations.append(
                    SalesObservation(
                        product_sku=product.sku,
                        business_date=business_date,
                        quantity=float(sold),
                        is_stockout_censored=stockout,
                    )
                )

    inventory: list[InventoryPosition] = []
    for product in expanded:
        base = BASE_DEMAND[product.sku.split("-")[0]] * _scale_for(product)
        inventory.append(
            InventoryPosition(
                product_sku=product.sku,
                saleable_on_hand=float(max(1, int(round(base * 0.45)))),
                remaining_shelf_life_days=max(1, product.shelf_life_days - 1),
            )
        )

    return SyntheticDataset(
        as_of_date=as_of,
        products=tuple(expanded),
        observations=tuple(observations),
        ground_truth=tuple(ground_truth),
        inventory=tuple(inventory),
        overrides=tuple(overrides),
    )
