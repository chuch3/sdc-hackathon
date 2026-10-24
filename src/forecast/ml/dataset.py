from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from ..contracts import ForecastContext, Product
from .features import (
    FeatureEncoder,
    ProductHistory,
    build_product_history,
)


@dataclass(frozen=True)
class TrainingExample:
    sku_index: int
    category_index: int
    features: tuple[float, ...]
    target: float
    target_date: date
    product_sku: str


def _product_dates(
    history: ProductHistory,
    start: date,
    end: date,
) -> list[date]:
    return sorted(
        day
        for day in history.daily
        if start <= day <= end and day not in history.censored
    )


def build_training_examples(
    context: ForecastContext,
    encoder: FeatureEncoder,
    min_history_days: int = 28,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    products: Sequence[Product] = tuple(context.products.values())
    for product in products:
        history = build_product_history(context, product.sku)
        available = sorted(history.daily)
        if not available:
            continue
        first_date = available[0] + timedelta(days=min_history_days)
        dates = _product_dates(
            history,
            start_date or first_date,
            end_date or date.max,
        )
        for target_date in dates:
            anchor = target_date - timedelta(days=1)
            sku_index, category_index, features = encoder.encode(
                product,
                history,
                target_date,
                anchor,
                context.overrides,
            )
            examples.append(
                TrainingExample(
                    sku_index=sku_index,
                    category_index=category_index,
                    features=tuple(features),
                    target=float(history.daily[target_date]),
                    target_date=target_date,
                    product_sku=product.sku,
                )
            )
    examples.sort(key=lambda item: (item.target_date, item.product_sku))
    return examples


def split_examples(
    examples: Sequence[TrainingExample],
    validation_fraction: float = 0.2,
) -> tuple[list[TrainingExample], list[TrainingExample]]:
    if not examples:
        return [], []
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1")
    sorted_examples = sorted(
        examples,
        key=lambda item: (item.target_date, item.product_sku),
    )
    unique_dates = sorted({item.target_date for item in sorted_examples})
    split_index = max(1, int(len(unique_dates) * (1.0 - validation_fraction)))
    cutoff = unique_dates[min(split_index, len(unique_dates) - 1)]
    train = [item for item in sorted_examples if item.target_date < cutoff]
    validation = [item for item in sorted_examples if item.target_date >= cutoff]
    if not train or not validation:
        midpoint = len(sorted_examples) // 2
        return sorted_examples[:midpoint], sorted_examples[midpoint:]
    return train, validation
