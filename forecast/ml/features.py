from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from ..contracts import (
    CalendarOverride,
    Domain,
    ForecastContext,
    Product,
)

NUMERIC_FEATURE_NAMES: tuple[str, ...] = (
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_7",
    "lag_14",
    "lag_28",
    "mean_7",
    "mean_28",
    "std_28",
    "cv_28",
    "days_since_sale",
    "horizon",
    "weekday",
    "weekday_sin",
    "weekday_cos",
    "is_weekend",
    "month_sin",
    "month_cos",
    "holiday_multiplier",
    "shelf_life_days",
    "lead_time_days",
    "moq",
    "safety_stock_days",
    "is_bakery",
)

NUMERIC_FEATURE_DIM = len(NUMERIC_FEATURE_NAMES)
UNKNOWN_INDEX = 0


@dataclass(frozen=True)
class FeatureVocabulary:
    skus: tuple[str, ...]
    categories: tuple[str, ...]

    @classmethod
    def from_products(cls, products: Iterable[Product]) -> "FeatureVocabulary":
        skus = sorted({product.sku for product in products})
        categories = sorted({product.category for product in products})
        return cls(skus=tuple(skus), categories=tuple(categories))

    @property
    def num_skus(self) -> int:
        return len(self.skus) + 1

    @property
    def num_categories(self) -> int:
        return len(self.categories) + 1

    def sku_index(self, sku: str) -> int:
        try:
            return self.skus.index(sku) + 1
        except ValueError:
            return UNKNOWN_INDEX

    def category_index(self, category: str) -> int:
        try:
            return self.categories.index(category) + 1
        except ValueError:
            return UNKNOWN_INDEX

    def to_dict(self) -> dict[str, Any]:
        return {"skus": list(self.skus), "categories": list(self.categories)}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "FeatureVocabulary":
        return cls(
            skus=tuple(str(item) for item in raw.get("skus", ())),
            categories=tuple(str(item) for item in raw.get("categories", ())),
        )


@dataclass(frozen=True)
class ProductHistory:
    daily: Mapping[date, float]
    censored: frozenset[date]
    last_sale_date: date | None
    dates: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        if not self.dates:
            object.__setattr__(self, "dates", tuple(sorted(self.daily)))

    def value(self, day: date) -> float:
        index = bisect_right(self.dates, day) - 1
        if index < 0:
            return 0.0
        return float(self.daily[self.dates[index]])

    def window_values(self, anchor: date, days: int) -> list[float]:
        start = anchor - timedelta(days=days - 1)
        return [
            float(value)
            for day, value in self.daily.items()
            if start <= day <= anchor
        ]


def build_product_history(
    context: ForecastContext,
    sku: str,
    as_of: date | None = None,
) -> ProductHistory:
    daily: dict[date, float] = {}
    censored: set[date] = set()
    for observation in context.sales_history:
        if observation.product_sku != sku:
            continue
        if as_of is not None and observation.business_date > as_of:
            continue
        if observation.is_stockout_censored:
            censored.add(observation.business_date)
            continue
        daily[observation.business_date] = (
            daily.get(observation.business_date, 0.0) + observation.quantity
        )
    last_sale_date = max(daily) if daily else None
    return ProductHistory(
        daily=daily,
        censored=frozenset(censored),
        last_sale_date=last_sale_date,
    )


def _holiday_multiplier(
    overrides: Sequence[CalendarOverride],
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


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    return statistics.pstdev(values) if len(values) >= 2 else 0.0


def raw_feature_vector(
    product: Product,
    history: ProductHistory,
    target_date: date,
    anchor_date: date,
    overrides: Sequence[CalendarOverride] = (),
) -> list[float]:
    if target_date <= anchor_date:
        raise ValueError("target_date must be after anchor_date")

    def lag(days: int) -> float:
        return history.value(anchor_date - timedelta(days=days - 1))

    week = history.window_values(anchor_date, 7)
    month = history.window_values(anchor_date, 28)
    mean_28 = _mean(month)
    std_28 = _std(month)
    past_sale_dates = [day for day in history.daily if day <= anchor_date]
    last_sale_before_anchor = max(past_sale_dates) if past_sale_dates else None
    days_since_sale = (
        (anchor_date - last_sale_before_anchor).days
        if last_sale_before_anchor is not None
        else 30
    )
    weekday = target_date.weekday()
    weekday_angle = 2.0 * math.pi * weekday / 7.0
    month_angle = 2.0 * math.pi * target_date.month / 12.0
    return [
        lag(1),
        lag(2),
        lag(3),
        lag(7),
        lag(14),
        lag(28),
        _mean(week),
        mean_28,
        std_28,
        std_28 / (mean_28 + 1.0),
        float(min(days_since_sale, 30)),
        float((target_date - anchor_date).days),
        float(weekday),
        math.sin(weekday_angle),
        math.cos(weekday_angle),
        1.0 if weekday >= 5 else 0.0,
        math.sin(month_angle),
        math.cos(month_angle),
        _holiday_multiplier(overrides, product, target_date),
        float(product.shelf_life_days),
        float(product.lead_time_days),
        float(product.moq),
        float(product.safety_stock_days),
        1.0 if product.domain is Domain.BAKERY else 0.0,
    ]


@dataclass(frozen=True)
class FeatureEncoder:
    vocabulary: FeatureVocabulary
    mean: tuple[float, ...]
    std: tuple[float, ...]

    @classmethod
    def fit(
        cls,
        vocabulary: FeatureVocabulary,
        vectors: Sequence[Sequence[float]],
    ) -> "FeatureEncoder":
        if not vectors:
            return cls(
                vocabulary=vocabulary,
                mean=tuple(0.0 for _ in NUMERIC_FEATURE_NAMES),
                std=tuple(1.0 for _ in NUMERIC_FEATURE_NAMES),
            )
        columns = list(zip(*vectors))
        mean = tuple(statistics.fmean(column) for column in columns)
        std = tuple(
            statistics.pstdev(column) if len(column) >= 2 else 1.0
            for column in columns
        )
        safe_std = tuple(value if value > 1e-9 else 1.0 for value in std)
        return cls(vocabulary=vocabulary, mean=mean, std=safe_std)

    def encode(
        self,
        product: Product,
        history: ProductHistory,
        target_date: date,
        anchor_date: date,
        overrides: Sequence[CalendarOverride] = (),
    ) -> tuple[int, int, list[float]]:
        raw = raw_feature_vector(
            product,
            history,
            target_date,
            anchor_date,
            overrides,
        )
        normalized = [
            (value - mean) / std
            for value, mean, std in zip(raw, self.mean, self.std)
        ]
        return (
            self.vocabulary.sku_index(product.sku),
            self.vocabulary.category_index(product.category),
            normalized,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vocabulary": self.vocabulary.to_dict(),
            "mean": list(self.mean),
            "std": list(self.std),
            "feature_names": list(NUMERIC_FEATURE_NAMES),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "FeatureEncoder":
        names = tuple(raw.get("feature_names", NUMERIC_FEATURE_NAMES))
        if names != NUMERIC_FEATURE_NAMES:
            raise ValueError("checkpoint feature schema does not match this code")
        return cls(
            vocabulary=FeatureVocabulary.from_dict(raw["vocabulary"]),
            mean=tuple(float(item) for item in raw["mean"]),
            std=tuple(float(item) for item in raw["std"]),
        )
