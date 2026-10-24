from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .contracts import (
    CalendarOverride,
    InventoryPosition,
    Product,
    SalesObservation,
)
from .synthetic import SyntheticDataset


class ForecastRepository(Protocol):
    def products(self) -> Sequence[Product]: ...

    def sales_history(self) -> Sequence[SalesObservation]: ...

    def inventory(self) -> Sequence[InventoryPosition]: ...

    def overrides(self) -> Sequence[CalendarOverride]: ...


@dataclass(frozen=True)
class InMemoryRepository:
    _products: tuple[Product, ...]
    _sales_history: tuple[SalesObservation, ...]
    _inventory: tuple[InventoryPosition, ...]
    _overrides: tuple[CalendarOverride, ...]

    @classmethod
    def from_synthetic(cls, dataset: SyntheticDataset) -> "InMemoryRepository":
        return cls(
            _products=dataset.products,
            _sales_history=dataset.observations,
            _inventory=dataset.inventory,
            _overrides=dataset.overrides,
        )

    @classmethod
    def from_records(
        cls,
        products: Sequence[Product],
        sales_history: Sequence[SalesObservation],
        inventory: Sequence[InventoryPosition],
        overrides: Sequence[CalendarOverride] = (),
    ) -> "InMemoryRepository":
        return cls(
            _products=tuple(products),
            _sales_history=tuple(sales_history),
            _inventory=tuple(inventory),
            _overrides=tuple(overrides),
        )

    def products(self) -> Sequence[Product]:
        return self._products

    def sales_history(self) -> Sequence[SalesObservation]:
        return self._sales_history

    def inventory(self) -> Sequence[InventoryPosition]:
        return self._inventory

    def overrides(self) -> Sequence[CalendarOverride]:
        return self._overrides
