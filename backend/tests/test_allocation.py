from datetime import date, timedelta
from decimal import Decimal

from app.services import allocation

ZERO = Decimal("0")


def batch(
    batch_id: int,
    expiry: date,
    quantity: str,
    *,
    received: date | None = None,
    status: str = "ACTIVE",
    unit_cost: str = "2.00",
) -> allocation.AllocationBatch:
    return allocation.AllocationBatch(
        id=batch_id,
        batch_code=f"B{batch_id}",
        expiry_date=expiry,
        received_date=received or expiry - timedelta(days=3),
        quantity_remaining=Decimal(quantity),
        unit_cost=Decimal(unit_cost),
        status=status,
    )


def test_fefo_order_sorts_by_expiry_then_receipt_then_id():
    today = date(2026, 10, 20)
    batches = [
        batch(3, today + timedelta(days=5), "10"),
        batch(2, today, "10", received=today - timedelta(days=1)),
        batch(1, today, "10", received=today - timedelta(days=2)),
        batch(4, today, "10", received=today - timedelta(days=2)),
    ]
    order = [item.id for item in allocation.fefo_order(batches)]
    assert order == [1, 4, 2, 3]


def test_plan_allocation_consumes_earliest_expiry_first():
    today = date(2026, 10, 20)
    batches = [
        batch(1, today + timedelta(days=5), "10"),
        batch(2, today + timedelta(days=1), "5"),
    ]
    plan = allocation.plan_allocation(batches, Decimal("7"))
    assert [item.batch_id for item in plan.allocations] == [2, 1]
    assert [item.quantity for item in plan.allocations] == [Decimal("5"), Decimal("2")]
    assert plan.allocated_quantity == Decimal("7")
    assert plan.shortfall == ZERO
    assert plan.is_fully_allocated is True


def test_plan_allocation_reports_shortfall_without_overselling():
    today = date(2026, 10, 20)
    batches = [batch(1, today + timedelta(days=1), "3")]
    plan = allocation.plan_allocation(batches, Decimal("8"))
    assert plan.allocated_quantity == Decimal("3")
    assert plan.shortfall == Decimal("5")
    assert plan.is_fully_allocated is False


def test_plan_allocation_does_not_mutate_the_batches():
    today = date(2026, 10, 20)
    batches = [batch(1, today + timedelta(days=1), "5")]
    allocation.plan_allocation(batches, Decimal("4"))
    assert batches[0].quantity_remaining == Decimal("5")


def test_saleable_candidates_exclude_expired_and_quarantined_stock():
    today = date(2026, 10, 20)
    batches = [
        batch(1, today + timedelta(days=1), "5"),
        batch(2, today - timedelta(days=1), "5"),
        batch(3, today + timedelta(days=1), "5", status="QUARANTINED"),
        batch(4, today + timedelta(days=1), "0"),
    ]
    saleable = allocation.saleable_candidates(batches, today)
    assert [item.id for item in saleable] == [1]
    assert allocation.available_quantity(saleable) == Decimal("5")


def test_removable_candidates_include_expired_and_quarantined_stock():
    today = date(2026, 10, 20)
    batches = [
        batch(1, today + timedelta(days=1), "5"),
        batch(2, today - timedelta(days=1), "5"),
        batch(3, today + timedelta(days=1), "5", status="QUARANTINED"),
        batch(4, today + timedelta(days=1), "5", status="CLOSED"),
    ]
    removable = allocation.removable_candidates(batches)
    assert sorted(item.id for item in removable) == [1, 2, 3]
    assert allocation.available_quantity(removable) == Decimal("15")


def test_plan_cost_uses_unit_cost():
    today = date(2026, 10, 20)
    batches = [batch(1, today + timedelta(days=1), "4", unit_cost="2.50")]
    plan = allocation.plan_allocation(batches, Decimal("4"))
    assert plan.cost == Decimal("10.00")
