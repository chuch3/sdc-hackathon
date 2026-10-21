"""Pure FEFO allocation logic.

The stock-action service and the week simulator must agree on which batch a
unit comes from. This module owns that decision and nothing else: no session,
no ORM models, no writes. Callers read their own rows, convert them to
``AllocationBatch`` values, and apply the returned plan to their own store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")
SELLABLE_STATUSES = frozenset({"ACTIVE"})
REMOVABLE_STATUSES = frozenset({"ACTIVE", "QUARANTINED"})


@dataclass(frozen=True)
class AllocationBatch:
    """A batch as the allocator sees it, free of any database dependency."""

    id: int
    batch_code: str
    expiry_date: date
    received_date: date
    quantity_remaining: Decimal
    unit_cost: Decimal = ZERO
    status: str = "ACTIVE"


@dataclass(frozen=True)
class Allocation:
    batch_id: int
    batch_code: str
    expiry_date: date
    received_date: date
    quantity: Decimal
    unit_cost: Decimal = ZERO

    @property
    def cost(self) -> Decimal:
        return self.quantity * self.unit_cost


@dataclass(frozen=True)
class AllocationPlan:
    requested_quantity: Decimal
    allocations: tuple[Allocation, ...] = ()

    @property
    def allocated_quantity(self) -> Decimal:
        return sum((item.quantity for item in self.allocations), ZERO)

    @property
    def shortfall(self) -> Decimal:
        return max(ZERO, self.requested_quantity - self.allocated_quantity)

    @property
    def is_fully_allocated(self) -> bool:
        return self.shortfall <= 0

    @property
    def cost(self) -> Decimal:
        return sum((item.cost for item in self.allocations), ZERO)


def fefo_order(batches) -> tuple[AllocationBatch, ...]:
    """Earliest expiry first, then earliest receipt, then batch id."""
    return tuple(
        sorted(batches, key=lambda batch: (batch.expiry_date, batch.received_date, batch.id))
    )


def saleable_candidates(batches, as_of: date) -> tuple[AllocationBatch, ...]:
    """Batches that may be sold on ``as_of``: active, unexpired, still holding stock."""
    return tuple(
        batch
        for batch in fefo_order(batches)
        if batch.status in SELLABLE_STATUSES
        and batch.expiry_date >= as_of
        and batch.quantity_remaining > 0
    )


def removable_candidates(batches) -> tuple[AllocationBatch, ...]:
    """Batches that may be written off or donated, including expired and quarantined stock."""
    return tuple(
        batch
        for batch in fefo_order(batches)
        if batch.status in REMOVABLE_STATUSES and batch.quantity_remaining > 0
    )


def available_quantity(batches) -> Decimal:
    return sum((batch.quantity_remaining for batch in batches), ZERO)


def plan_allocation(batches, quantity: Decimal) -> AllocationPlan:
    """Split ``quantity`` across ``batches`` in FEFO order without mutating them."""
    requested = Decimal(str(quantity))
    remaining = requested
    allocations: list[Allocation] = []
    for batch in fefo_order(batches):
        if remaining <= 0:
            break
        if batch.quantity_remaining <= 0:
            continue
        take = min(batch.quantity_remaining, remaining)
        allocations.append(
            Allocation(
                batch_id=batch.id,
                batch_code=batch.batch_code,
                expiry_date=batch.expiry_date,
                received_date=batch.received_date,
                quantity=take,
                unit_cost=batch.unit_cost,
            )
        )
        remaining -= take
    return AllocationPlan(requested_quantity=requested, allocations=tuple(allocations))
