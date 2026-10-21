"""Read-only seven-day projection and quest-board cards.

The planner never writes to the database. It reads the current ledger, projects
stock forward day by day using the shared FEFO allocator, and turns that
projection into small, explainable action cards for the weekly quest board.

Money figures use batch unit cost, not retail price, so every monetary number
is a cost-based estimate and is labelled as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import Settings
from app.db import utc_now
from app.services import allocation
from app.services.forecast_repository import build_pipeline
from app.services.recommendations import CONFIDENCE

ZERO = Decimal("0")
CARD_ORDER = {
    "WRITE_OFF": 0,
    "STOCKOUT": 1,
    "SELL_FIRST": 2,
    "RECEIVE_ORDER": 3,
    "MARKDOWN": 4,
    "BUY": 5,
    "BAKE": 5,
    "DONATE": 6,
    "DATA_WARNING": 7,
    "HOLD": 8,
}
CARD_LABELS = {
    "STOCKOUT": "Stockout",
    "SELL_FIRST": "Sell first",
    "MARKDOWN": "Markdown",
    "DONATE": "Donate",
    "WRITE_OFF": "Write off",
    "RECEIVE_ORDER": "Receive order",
    "BUY": "Buy",
    "BAKE": "Bake",
    "HOLD": "Hold",
    "DATA_WARNING": "Check data",
}
ASSUMPTIONS = [
    "Money figures use batch unit cost, not retail price; treat them as cost-based estimates.",
    "Demand comes from the forecast engine only; receipts, waste, and donations are never "
    "counted as demand.",
    "The plan is a read-only projection. It does not change stock, orders, or approvals.",
    "Expected sales assume the plan is followed and that expired stock is never sold.",
]


def _cost(value: Decimal) -> Decimal:
    """Money is reported with two decimal places, like every other money figure."""
    return value.quantize(Decimal("0.01"))


def _money(value: Decimal) -> str:
    return f"${_cost(value):,.2f}"


def _quantity(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.001')):,.3f}".rstrip("0").rstrip(".")


@dataclass
class ProjectedBatch:
    id: int
    product_id: int
    batch_code: str
    expiry_date: date
    received_date: date
    quantity: Decimal
    unit_cost: Decimal
    status: str = "ACTIVE"
    source: str = "on_hand"


@dataclass
class Arrival:
    order_id: int
    supplier_id: int
    expected_date: date
    arrival_date: date
    overdue: bool
    product_id: int
    sku: str
    product_name: str
    quantity: Decimal
    unit_cost: Decimal
    expiry_date: date


@dataclass(frozen=True)
class Leftover:
    """Snapshot of a batch that is still saleable at the end of a projected day."""

    batch_id: int
    batch_code: str
    expiry_date: date
    quantity: Decimal
    unit_cost: Decimal


@dataclass
class DayState:
    date: date
    starting_stock: Decimal = ZERO
    arrivals: Decimal = ZERO
    expected_sales: Decimal = ZERO
    unmet_demand: Decimal = ZERO
    ending_stock: Decimal = ZERO
    expired_quantity: Decimal = ZERO
    expired_cost: Decimal = ZERO
    at_risk_quantity: Decimal = ZERO
    at_risk_cost: Decimal = ZERO
    at_risk_expiry: date | None = None
    rescued_quantity: Decimal = ZERO
    rescued_cost: Decimal = ZERO
    at_risk: list[Leftover] = field(default_factory=list)
    leftover: list[Leftover] = field(default_factory=list)


@dataclass
class ProductPlan:
    product: models.Product
    sku: str
    name: str
    unit: str
    domain: str
    threshold: int
    lead_time_days: int
    batches: list[ProjectedBatch]
    expired_before: list[ProjectedBatch]
    quarantined: list[ProjectedBatch]
    demand: dict[date, Decimal]
    arrivals: dict[date, list[Arrival]]
    recommendation: object
    confidence: float
    data_reliable: bool = True
    expiring_this_week_cost: Decimal = ZERO
    flagged_batches: set[int] = field(default_factory=set)
    days: dict[date, DayState] = field(default_factory=dict)
    shortage_day: date | None = None
    last_shortage_day: date | None = None

    @property
    def cost_per_unit(self) -> Decimal:
        """Weighted average unit cost of the projected stock on hand."""
        quantity = sum((batch.quantity for batch in self.batches), ZERO)
        if quantity <= 0:
            return ZERO
        value = sum((batch.quantity * batch.unit_cost for batch in self.batches), ZERO)
        return value / quantity


def _as_batch(batch: ProjectedBatch) -> allocation.AllocationBatch:
    return allocation.AllocationBatch(
        id=batch.id,
        batch_code=batch.batch_code,
        expiry_date=batch.expiry_date,
        received_date=batch.received_date,
        quantity_remaining=batch.quantity,
        unit_cost=batch.unit_cost,
        status=batch.status,
    )


def _on_hand_batches(db: Session) -> list[ProjectedBatch]:
    rows = db.scalars(
        select(models.Batch)
        .where(models.Batch.quantity_remaining > 0)
        .order_by(models.Batch.product_id, models.Batch.expiry_date, models.Batch.id)
    ).all()
    return [
        ProjectedBatch(
            id=batch.id,
            product_id=batch.product_id,
            batch_code=batch.batch_code,
            expiry_date=batch.expiry_date,
            received_date=batch.received_date,
            quantity=Decimal(batch.quantity_remaining),
            unit_cost=Decimal(batch.unit_cost),
            status=batch.status,
        )
        for batch in rows
    ]


def _arrivals(
    db: Session,
    rows_by_id: dict[int, models.Product],
    board_start: date,
    horizon_end: date,
) -> dict[date, list[Arrival]]:
    """Approved purchase orders only. Overdue orders land on the first board day."""
    grouped: dict[date, list[Arrival]] = {}
    orders = db.scalars(
        select(models.PurchaseOrder)
        .where(models.PurchaseOrder.status == "APPROVED")
        .order_by(models.PurchaseOrder.expected_date, models.PurchaseOrder.id)
    ).all()
    for order in orders:
        for line in order.lines:
            outstanding = Decimal(line.quantity) - Decimal(line.received_quantity)
            if outstanding <= 0:
                continue
            product = rows_by_id.get(line.product_id)
            if product is None:
                continue
            overdue = order.expected_date < board_start
            arrival_date = board_start if overdue else order.expected_date
            if arrival_date > horizon_end:
                continue
            arrival = Arrival(
                order_id=order.id,
                supplier_id=order.supplier_id,
                expected_date=order.expected_date,
                arrival_date=arrival_date,
                overdue=overdue,
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                quantity=outstanding,
                unit_cost=Decimal(line.unit_cost),
                expiry_date=arrival_date + timedelta(days=product.shelf_life_days),
            )
            grouped.setdefault(arrival_date, []).append(arrival)
    return grouped


def _card(
    kind: str,
    priority: str,
    *,
    plan: ProductPlan | None = None,
    product_id: int | None = None,
    product_sku: str = "",
    product_name: str = "",
    quantity: Decimal = ZERO,
    unit: str = "",
    deadline: date | None = None,
    summary: str = "",
    why: list[str] | None = None,
    confidence: float = 0.35,
    expiry_risk: str = "healthy",
    impact: str = "",
    calculation: dict[str, float] | None = None,
) -> schemas.PlannerCard:
    return schemas.PlannerCard(
        kind=kind,
        priority=priority,
        product_id=product_id if product_id is not None else (plan.product.id if plan else None),
        product_sku=product_sku or (plan.sku if plan else ""),
        product_name=product_name or (plan.name if plan else ""),
        quantity=quantity,
        unit=unit or (plan.unit if plan else ""),
        deadline=deadline,
        summary=summary,
        why=why or [],
        confidence=confidence,
        expiry_risk=expiry_risk,
        impact=impact,
        calculation=calculation or {},
    )


def _project(plan: ProductPlan, days: list[date], board_start: date, horizon_end: date) -> None:
    """Walk forward one day at a time: arrivals, then sales, then end-of-day expiry."""
    next_id = 10_000
    for day in days:
        state = DayState(date=day)
        state.starting_stock = sum(
            (
                batch.quantity
                for batch in plan.batches
                if batch.status == "ACTIVE"
                and batch.expiry_date >= day
                and batch.quantity > 0
            ),
            ZERO,
        )

        for arrival in plan.arrivals.get(day, []):
            next_id += 1
            plan.batches.append(
                ProjectedBatch(
                    id=next_id,
                    product_id=plan.product.id,
                    batch_code=f"PO-{arrival.order_id}-{arrival.sku}",
                    expiry_date=arrival.expiry_date,
                    received_date=day,
                    quantity=arrival.quantity,
                    unit_cost=arrival.unit_cost,
                    status="ACTIVE",
                    source="purchase_order",
                )
            )
            state.arrivals += arrival.quantity

        at_risk = [
            Leftover(
                batch_id=batch.id,
                batch_code=batch.batch_code,
                expiry_date=batch.expiry_date,
                quantity=batch.quantity,
                unit_cost=batch.unit_cost,
            )
            for batch in plan.batches
            if batch.quantity > 0
            and batch.status == "ACTIVE"
            and batch.expiry_date >= day
            and (batch.expiry_date - day).days <= plan.threshold
        ]
        state.at_risk = at_risk
        state.at_risk_quantity = sum((batch.quantity for batch in at_risk), ZERO)
        state.at_risk_cost = _cost(
            sum((batch.quantity * batch.unit_cost for batch in at_risk), ZERO)
        )
        state.at_risk_expiry = min(
            (batch.expiry_date for batch in at_risk), default=None
        )

        demand = plan.demand.get(day, ZERO)
        candidates = allocation.saleable_candidates(
            [_as_batch(batch) for batch in plan.batches], day
        )
        result = allocation.plan_allocation(candidates, demand)
        by_id = {batch.id: batch for batch in plan.batches}
        for item in result.allocations:
            source = by_id.get(item.batch_id)
            if source is None:
                continue
            source.quantity -= item.quantity
            if source.expiry_date <= horizon_end:
                state.rescued_quantity += item.quantity
                state.rescued_cost += _cost(item.quantity * item.unit_cost)
        state.expected_sales = result.allocated_quantity
        state.unmet_demand = result.shortfall
        if state.unmet_demand > 0:
            if plan.shortage_day is None:
                plan.shortage_day = day
            plan.last_shortage_day = day

        for batch in plan.batches:
            if batch.quantity <= 0 or batch.expiry_date > day:
                continue
            state.expired_quantity += batch.quantity
            state.expired_cost += _cost(batch.quantity * batch.unit_cost)
            batch.quantity = ZERO

        leftover = [
            Leftover(
                batch_id=batch.id,
                batch_code=batch.batch_code,
                expiry_date=batch.expiry_date,
                quantity=batch.quantity,
                unit_cost=batch.unit_cost,
            )
            for batch in plan.batches
            if batch.quantity > 0 and batch.status == "ACTIVE"
        ]
        state.leftover = leftover
        state.ending_stock = sum((batch.quantity for batch in leftover), ZERO)
        plan.days[day] = state


def _demand_before(plan: ProductPlan, day: date, deadline: date) -> Decimal:
    """Expected sales from ``day`` up to and including ``deadline``."""
    return sum(
        (
            plan.demand.get(day + timedelta(days=offset), ZERO)
            for offset in range(0, max((deadline - day).days, 0) + 1)
        ),
        ZERO,
    )


def _sell_first_cards(plan: ProductPlan, day: date, state: DayState) -> list[schemas.PlannerCard]:
    expiring = [
        batch
        for batch in state.at_risk
        if batch.batch_id not in plan.flagged_batches
    ]
    if not expiring:
        return []
    quantity = sum((batch.quantity for batch in expiring), ZERO)
    deadline = min(batch.expiry_date for batch in expiring)
    cost = sum((batch.quantity * batch.unit_cost for batch in expiring), ZERO)
    days_left = (deadline - day).days
    plan.flagged_batches.update(batch.batch_id for batch in expiring)
    demand_before = _demand_before(plan, day, deadline)
    if plan.data_reliable:
        demand_why = (
            f"Expected sales before {deadline.isoformat()} are only "
            f"{_quantity(demand_before)} {plan.unit}."
        )
    else:
        demand_why = (
            "Expected sales are unknown for this product, so the expiry date is the "
            "hard constraint."
        )
    surplus = max(ZERO, quantity - demand_before)
    if plan.data_reliable:
        surplus_line = (
            f"About {_quantity(surplus)} {plan.unit} will not sell in time; "
            "mark that part down before it expires."
            if surplus > 0
            else "The forecast expects this stock to sell in time."
        )
    else:
        surplus_line = (
            "Expected sales are unknown for this product, so use this stock first."
        )
    return [
        _card(
            "SELL_FIRST",
            "critical" if days_left == 0 else "warning",
            plan=plan,
            quantity=quantity,
            deadline=deadline,
            summary=(
                f"Sell or mark down {_quantity(quantity)} {plan.unit} of {plan.name} "
                f"before {deadline.isoformat()}."
            ),
            why=[
                f"{_quantity(quantity)} {plan.unit} in stock expire on "
                f"{deadline.isoformat()}.",
                demand_why,
                surplus_line,
            ],
            confidence=plan.confidence,
            expiry_risk="critical" if days_left == 0 else "warning",
            impact=f"Avoids about {_money(cost)} of write-off (cost-based estimate).",
            calculation={
                "near_expiry_quantity": float(quantity),
                "forecast_before_expiry": float(demand_before),
                "surplus": float(surplus),
                "cost_at_risk": float(cost),
            },
        )
    ]


def _markdown_cards(
    plan: ProductPlan, day: date, state: DayState, last_demand_day: date
) -> list[schemas.PlannerCard]:
    cards = []
    if not plan.data_reliable:
        return cards
    for batch in state.leftover:
        days_to_expiry = (batch.expiry_date - day).days
        if days_to_expiry <= plan.threshold or batch.expiry_date > last_demand_day:
            continue
        if batch.batch_id in plan.flagged_batches:
            continue
        demand_before = sum(
            (
                plan.demand.get(day + timedelta(days=offset), ZERO)
                for offset in range(1, days_to_expiry + 1)
            ),
            ZERO,
        )
        surplus = batch.quantity - demand_before
        if surplus <= 0:
            continue
        plan.flagged_batches.add(batch.batch_id)
        cost = surplus * batch.unit_cost
        cards.append(
            _card(
                "MARKDOWN",
                "warning",
                plan=plan,
                quantity=surplus,
                deadline=batch.expiry_date,
                summary=(
                    f"Mark down {_quantity(surplus)} {plan.unit} of {plan.name}; "
                    f"expected sales before expiry are only "
                    f"{_quantity(demand_before)} {plan.unit}."
                ),
                why=[
                    f"{_quantity(batch.quantity)} {plan.unit} remain in stock.",
                    f"Forecast demand before {batch.expiry_date.isoformat()} is "
                    f"{_quantity(demand_before)} {plan.unit}.",
                    "Markdown recovers value before the batch expires.",
                ],
                confidence=plan.confidence,
                expiry_risk="warning",
                impact=f"Recovers about {_money(cost)} instead of writing it off.",
                calculation={
                    "saleable_on_hand": float(batch.quantity),
                    "forecast_before_expiry": float(demand_before),
                    "surplus": float(surplus),
                    "cost_at_risk": float(cost),
                },
            )
        )
    return cards


def _write_off_cards(plan: ProductPlan, day: date, state: DayState) -> list[schemas.PlannerCard]:
    if state.expired_quantity <= 0:
        return []
    return [
        _card(
            "WRITE_OFF",
            "critical",
            plan=plan,
            quantity=state.expired_quantity,
            deadline=day,
            summary=(
                f"Write off {_quantity(state.expired_quantity)} {plan.unit} of "
                f"{plan.name}; it expires on {day.isoformat()}."
            ),
            why=[
                "The batch reaches its expiry date with stock still on hand.",
                "Expired food is never sold, donated, or baked.",
                "Record the write-off so the ledger stays balanced.",
            ],
            confidence=plan.confidence,
            expiry_risk="expired",
            impact=(
                f"Clears about {_money(state.expired_cost)} of expired stock "
                "(cost-based estimate)."
            ),
            calculation={
                "expired_quantity": float(state.expired_quantity),
                "expired_cost": float(state.expired_cost),
            },
        )
    ]


def _expired_stock_card(
    plans: list[ProductPlan], board_start: date
) -> schemas.PlannerCard | None:
    """One card for the stock that was already expired when the plan starts."""
    expired = [
        (plan, batch)
        for plan in plans
        for batch in plan.expired_before
        if batch.quantity > 0
    ]
    if not expired:
        return None
    quantity = sum((batch.quantity for _, batch in expired), ZERO)
    cost = sum((batch.quantity * batch.unit_cost for _, batch in expired), ZERO)
    products = sorted({plan.name for plan, _ in expired})
    return _card(
        "WRITE_OFF",
        "critical",
        product_id=None,
        product_sku="",
        product_name=f"Expired stock ({len(products)} products)",
        quantity=quantity,
        unit="units",
        deadline=max(batch.expiry_date for _, batch in expired),
        summary=(
            f"Clear {_quantity(quantity)} units of stock that expired before "
            f"{board_start.isoformat()}; it can never be sold or donated."
        ),
        why=[
            f"{len(products)} products still hold expired stock on the shelf.",
            "Expired food is never sold, donated, or baked.",
            "Record the write-off on the Expiry page so the ledger stays balanced.",
        ],
        confidence=1.0,
        expiry_risk="expired",
        impact=f"Clears about {_money(cost)} of unsellable stock (cost-based estimate).",
        calculation={
            "expired_quantity": float(quantity),
            "expired_cost": float(cost),
            "products_affected": float(len(products)),
        },
    )


def _stockout_cards(
    plans: list[ProductPlan],
    day: date,
    board_start: date,
    emitted: set[int],
    covered: set[int] | None = None,
) -> list[schemas.PlannerCard]:
    """One card per day for the products whose projected shortage starts now."""
    gaps = []
    for plan in plans:
        state = plan.days[day]
        if state.unmet_demand <= 0 or plan.product.id in emitted:
            continue
        if covered and plan.product.id in covered:
            # A buy or bake task already answers this shortage.
            continue
        emitted.add(plan.product.id)
        gaps.append((plan, state))
    if not gaps:
        return []
    total = sum((state.unmet_demand for _, state in gaps), ZERO)
    why = []
    for plan, state in gaps:
        available = state.starting_stock + state.arrivals
        first = max(plan.shortage_day or day, board_start)
        last = plan.last_shortage_day or day
        span = (
            f" Short from {first.isoformat()} to {last.isoformat()}."
            if first != last
            else ""
        )
        why.append(
            f"{plan.name}: {_quantity(state.unmet_demand)} {plan.unit} short. "
            f"{_quantity(state.expected_sales + state.unmet_demand)} {plan.unit} are "
            f"expected to sell and only {_quantity(available)} {plan.unit} are in stock "
            f"at the start of the day.{span}"
        )
    why.append("Expanding the order or accepting lost sales are the two options.")
    why.append("Expired or quarantined stock can never cover the gap.")
    names = ", ".join(plan.name for plan, _ in gaps)
    single = len(gaps) == 1
    expected = sum((state.expected_sales + state.unmet_demand for _, state in gaps), ZERO)
    available = sum(
        (state.starting_stock + state.arrivals for _, state in gaps), ZERO
    )
    summary = (
        f"Projected stockout: {_quantity(total)} {gaps[0][0].unit} of {names} "
        f"cannot be sold on {day.isoformat()}."
        if single
        else (
            f"Projected stockout on {day.isoformat()}: {_quantity(total)} units across "
            f"{len(gaps)} products cannot be sold."
        )
    )
    return [
        _card(
            "STOCKOUT",
            "critical",
            product_id=gaps[0][0].product.id if single else None,
            product_sku=gaps[0][0].sku if single else "",
            product_name=gaps[0][0].name if single else f"{len(gaps)} products",
            quantity=total,
            unit=gaps[0][0].unit if single else "units",
            deadline=day,
            summary=summary,
            why=why,
            confidence=min(plan.confidence for plan, _ in gaps),
            expiry_risk="healthy",
            impact=(
                f"About {_quantity(total)} units of expected sales cannot be met on "
                "this day. Order earlier or plan for the lost sales."
            ),
            calculation={
                "expected_sales": float(expected),
                "available_at_start": float(available),
                "shortfall": float(total),
                "products_short": float(len(gaps)),
            },
        )
    ]


def _quarantined_card(
    plan: ProductPlan, batches: list[ProjectedBatch]
) -> schemas.PlannerCard | None:
    if not batches:
        return None
    quantity = sum((batch.quantity for batch in batches), ZERO)
    cost = sum((batch.quantity * batch.unit_cost for batch in batches), ZERO)
    return _card(
        "WRITE_OFF",
        "critical",
        plan=plan,
        quantity=quantity,
        deadline=min(batch.expiry_date for batch in batches),
        summary=(
            f"Quarantined stock: dispose of {_quantity(quantity)} {plan.unit} of "
            f"{plan.name}; it can never be sold."
        ),
        why=[
            "Quarantined batches are blocked from sale and from donation.",
            "They still sit on the shelf until they are written off.",
            "Dispose of them through the normal approval flow.",
        ],
        confidence=plan.confidence,
        expiry_risk="expired",
        impact=f"Clears about {_money(cost)} of unsellable stock (cost-based estimate).",
        calculation={
            "quarantined_quantity": float(quantity),
            "quarantined_cost": float(cost),
        },
    )


def _peak_shortage(plan: ProductPlan) -> Decimal:
    """The largest daily shortfall the projection expects."""
    return max(
        (state.unmet_demand for state in plan.days.values()),
        default=ZERO,
    )


def _replenishment_card(plan: ProductPlan) -> schemas.PlannerCard | None:
    recommendation = plan.recommendation
    action = recommendation.action.value
    quantity = Decimal(str(round(float(recommendation.quantity), 3)))
    shortfall = _peak_shortage(plan)
    if action not in {"BUY", "BAKE"}:
        if plan.shortage_day is None or shortfall <= 0:
            return None
        # The projection says stock runs out even though today's reorder check
        # says hold, so the board still needs a task to answer the shortage.
        action = "BAKE" if plan.domain == "bakery" else "BUY"
        case_size = max(1, int(plan.product.case_size or 1))
        quantity = (shortfall / case_size).to_integral_value(rounding="ROUND_CEILING") * case_size
    order_by = None
    if plan.shortage_day is not None:
        order_by = plan.shortage_day - timedelta(days=plan.lead_time_days)
    priority = "critical" if plan.shortage_day is not None else "warning"
    verb = "Bake" if action == "BAKE" else "Buy"
    calculation = {key: float(value) for key, value in recommendation.calculation.items()}
    why = list(recommendation.why)
    if plan.shortage_day is not None:
        why.insert(
            0, f"Projected stock runs short on {plan.shortage_day.isoformat()}."
        )
        if shortfall > 0:
            why.insert(
                1,
                f"The projection expects up to {_quantity(shortfall)} {plan.unit} of "
                "unmet demand on that day.",
            )
    if order_by is not None:
        why.insert(
            2 if shortfall > 0 else 1,
            f"Order by {order_by.isoformat()} to cover the {plan.lead_time_days} "
            "day lead time.",
        )
    calculation["projected_shortfall"] = float(shortfall)
    return _card(
        action,
        priority,
        plan=plan,
        quantity=quantity,
        deadline=order_by,
        summary=(
            f"{verb} {_quantity(quantity)} {plan.unit} of {plan.name}"
            + (
                f" to arrive before {plan.shortage_day.isoformat()}."
                if plan.shortage_day is not None
                else "."
            )
        ),
        why=why,
        confidence=plan.confidence,
        expiry_risk=recommendation.expiry_risk,
        impact=(
            "Keeps the projected gap covered for the reorder window."
            if plan.shortage_day is None
            else f"Covers the projected shortfall on {plan.shortage_day.isoformat()}."
        ),
        calculation=calculation,
    )


def _data_warning_card(plan: ProductPlan) -> schemas.PlannerCard | None:
    forecast = plan.recommendation.forecast
    quality = forecast.data_quality
    codes = {code.value for code in forecast.reason_codes}
    problems = []
    if "NO_HISTORY" in codes:
        problems.append("there is no usable sales history for this product")
    if quality.stale or "STALE_DATA" in codes:
        problems.append("the last sale is older than three days")
    if quality.cold_start or "COLD_START_CATEGORY_FALLBACK" in codes:
        problems.append("there is too little history, so the category average is used")
    if not forecast.actionable and not problems:
        problems.append("the forecast is not actionable until the data improves")
    if not problems:
        return None
    return _card(
        "DATA_WARNING",
        "warning",
        plan=plan,
        quantity=ZERO,
        summary=f"Check the sales data for {plan.name} before acting on the plan.",
        why=[f"For {plan.name}, {problem}." for problem in problems]
        + ["Fix the data so the forecast and this plan stay trustworthy."],
        confidence=plan.confidence,
        expiry_risk=plan.recommendation.expiry_risk,
        impact="Unlocks a trustworthy forecast for this product.",
        calculation={
            "valid_days": float(quality.valid_days),
            "history_days": float(quality.history_days),
            "censored_days": float(quality.censored_days),
        },
    )


def _receive_order_card(arrivals: list[Arrival]) -> schemas.PlannerCard:
    order_id = arrivals[0].order_id
    quantity = sum((item.quantity for item in arrivals), ZERO)
    overdue = arrivals[0].overdue
    return _card(
        "RECEIVE_ORDER",
        "warning" if overdue else "info",
        product_id=None,
        product_sku="",
        product_name=f"Purchase order #{order_id}",
        quantity=quantity,
        unit="unit",
        deadline=arrivals[0].arrival_date,
        summary=(
            f"Receive purchase order #{order_id}: {_quantity(quantity)} units arrive"
            + (" (overdue)." if overdue else ".")
        ),
        why=[
            f"Approved order #{order_id} was expected on "
            f"{arrivals[0].expected_date.isoformat()}.",
            "Received stock becomes saleable with a shelf life counted from the arrival date.",
            "Draft and cancelled orders are ignored by the planner.",
        ],
        confidence=1.0,
        expiry_risk="healthy",
        impact="Adds incoming stock to the projected balance.",
        calculation={
            "arriving_quantity": float(quantity),
            "overdue": 1.0 if overdue else 0.0,
        },
    )


def _headline(cards: list[schemas.PlannerCard]) -> str:
    if not cards:
        return "Nothing needs attention."
    top = cards[0]
    return f"{CARD_LABELS.get(top.kind, top.kind.title())}: {top.summary}"


def _badges(
    days_out: list[schemas.PlannerDay],
    waste_free_days: int,
    stockout_days: int,
    clean_days: int,
    rescued_cost: Decimal,
) -> list[schemas.PlannerBadge]:
    markdown_days = sum(
        1 for day in days_out if any(card.kind == "MARKDOWN" for card in day.cards)
    )
    total = len(days_out) or 1
    return [
        schemas.PlannerBadge(
            code="zero_waste_day",
            label="Zero Waste Day",
            earned=waste_free_days > 0,
            detail=f"{waste_free_days} of {total} days have no projected write-off.",
        ),
        schemas.PlannerBadge(
            code="markdown_hero",
            label="Markdown Hero",
            earned=markdown_days > 0,
            detail=f"{markdown_days} day(s) include a markdown action.",
        ),
        schemas.PlannerBadge(
            code="stockout_slayer",
            label="Stockout Slayer",
            earned=stockout_days == 0,
            detail=f"{stockout_days} day(s) with a projected stockout.",
        ),
        schemas.PlannerBadge(
            code="fefo_apprentice",
            label="FEFO Apprentice",
            earned=rescued_cost > 0,
            detail=f"About {_money(rescued_cost)} of near-expiry stock sells before expiry.",
        ),
        schemas.PlannerBadge(
            code="data_detective",
            label="Data Detective",
            earned=not any(
                card.kind == "DATA_WARNING" for day in days_out for card in day.cards
            ),
            detail="No stale or missing sales data flagged this week.",
        ),
        schemas.PlannerBadge(
            code="perfect_week",
            label="Perfect Week",
            earned=clean_days == total and stockout_days == 0,
            detail=f"{clean_days} of {total} days have a clean plan.",
        ),
    ]


def build_week(
    db: Session,
    as_of: date | None = None,
    start: date | None = None,
    days: int = 7,
    settings: Settings | None = None,
) -> schemas.PlannerWeek:
    """Project the next ``days`` days and return the weekly quest board."""
    settings = settings or Settings()
    as_of = as_of or settings.business_today()
    if days < 1 or days > 14:
        raise ValueError("days must be between 1 and 14")
    board_start = start or (as_of + timedelta(days=1))
    if board_start <= as_of:
        raise ValueError("start must be after the business date")
    if board_start > as_of + timedelta(days=30):
        raise ValueError("start must be within 30 days of the business date")
    board_end = board_start + timedelta(days=days - 1)
    horizon = (board_end - as_of).days

    pipeline = build_pipeline(db, as_of, settings)
    repository = pipeline.repository
    context = pipeline.build_context(as_of)
    rows = list(db.scalars(select(models.Product).order_by(models.Product.id)))
    rows_by_id = {row.id: row for row in rows}
    rows_by_sku = {row.sku: row for row in rows}
    on_hand = _on_hand_batches(db)
    arrivals = _arrivals(db, rows_by_id, board_start, board_end)
    projection_days = [as_of + timedelta(days=offset) for offset in range(1, horizon + 1)]

    plans: list[ProductPlan] = []
    for product in repository.products():
        row = rows_by_sku.get(product.sku)
        if row is None:
            continue
        policy = repository.policies.policies_for(product)
        forecast = pipeline.forecaster.forecast(
            repository.contracts.ForecastRequest(
                product_sku=product.sku,
                as_of_date=as_of,
                horizon_days=horizon,
            ),
            context,
            policy.demand,
        )
        recommendation = pipeline.recommend_one(product.sku, as_of, context)
        product_batches = [batch for batch in on_hand if batch.product_id == row.id]
        live_batches = [
            ProjectedBatch(
                id=batch.id,
                product_id=batch.product_id,
                batch_code=batch.batch_code,
                expiry_date=batch.expiry_date,
                received_date=batch.received_date,
                quantity=batch.quantity,
                unit_cost=batch.unit_cost,
                status=batch.status,
            )
            for batch in product_batches
            if batch.status == "ACTIVE" and batch.expiry_date > as_of
        ]
        codes = {code.value for code in recommendation.forecast.reason_codes}
        plans.append(
            ProductPlan(
                product=row,
                sku=product.sku,
                name=product.name,
                unit=product.unit,
                domain=product.domain,
                threshold=product.near_expiry_threshold_days,
                lead_time_days=product.lead_time_days,
                batches=live_batches,
                expired_before=[
                    ProjectedBatch(
                        id=batch.id,
                        product_id=batch.product_id,
                        batch_code=batch.batch_code,
                        expiry_date=batch.expiry_date,
                        received_date=batch.received_date,
                        quantity=batch.quantity,
                        unit_cost=batch.unit_cost,
                        status=batch.status,
                    )
                    for batch in product_batches
                    if batch.expiry_date <= as_of
                ],
                quarantined=[
                    ProjectedBatch(
                        id=batch.id,
                        product_id=batch.product_id,
                        batch_code=batch.batch_code,
                        expiry_date=batch.expiry_date,
                        received_date=batch.received_date,
                        quantity=batch.quantity,
                        unit_cost=batch.unit_cost,
                        status=batch.status,
                    )
                    for batch in product_batches
                    if batch.status == "QUARANTINED" and batch.expiry_date > as_of
                ],
                demand={
                    item.forecast_date: Decimal(str(round(item.quantity, 3)))
                    for item in forecast.daily
                },
                arrivals={
                    day: [item for item in items if item.product_id == row.id]
                    for day, items in arrivals.items()
                },
                recommendation=recommendation,
                confidence=CONFIDENCE.get(recommendation.confidence.value, 0.35),
                data_reliable=(
                    "NO_HISTORY" not in codes
                    and not recommendation.forecast.data_quality.cold_start
                ),
                expiring_this_week_cost=_cost(
                    sum(
                        (
                            batch.quantity * batch.unit_cost
                            for batch in live_batches
                            if batch.expiry_date <= board_end
                        ),
                        ZERO,
                    )
                ),
            )
        )

    for plan in plans:
        _project(plan, projection_days, board_start, board_end)

    last_demand_day = max(
        (day for plan in plans for day in plan.demand), default=board_end
    )

    day_cards: dict[date, list[schemas.PlannerCard]] = {day: [] for day in projection_days}
    orders_due: dict[date, list[schemas.PlannerOrderDue]] = {day: [] for day in projection_days}
    stockout_emitted: set[int] = set()

    for plan in plans:
        for day in projection_days:
            state = plan.days[day]
            if day == board_start:
                quarantine_card = _quarantined_card(plan, plan.quarantined)
                if quarantine_card is not None:
                    day_cards[day].append(quarantine_card)
            expiry_cards = _sell_first_cards(plan, day, state)
            expiry_cards.extend(_markdown_cards(plan, day, state, last_demand_day))
            write_off_cards = _write_off_cards(plan, day, state)
            if expiry_cards:
                # The sell or markdown task already covers this stock. Asking for a
                # write-off on the same day would contradict it.
                write_off_cards = []
            day_cards[day].extend(expiry_cards)
            day_cards[day].extend(write_off_cards)

    expired_card = _expired_stock_card(plans, board_start)
    if expired_card is not None:
        day_cards[board_start].append(expired_card)

    replenished: set[int] = set()
    for plan in plans:
        card = _replenishment_card(plan)
        if card is not None:
            replenished.add(plan.product.id)
            target = board_start
            if plan.shortage_day is not None:
                order_by = plan.shortage_day - timedelta(days=plan.lead_time_days)
                target = min(board_end, max(board_start, order_by))
            day_cards[target].append(card)
        warning = _data_warning_card(plan)
        if warning is not None:
            day_cards[board_start].append(warning)

    for day in projection_days:
        if day < board_start:
            continue
        day_cards[day].extend(
            _stockout_cards(plans, day, board_start, stockout_emitted)
        )

    for day in projection_days:
        by_order: dict[int, list[Arrival]] = {}
        for arrival in arrivals.get(day, []):
            by_order.setdefault(arrival.order_id, []).append(arrival)
        for order_id in sorted(by_order):
            lines = by_order[order_id]
            orders_due[day].append(
                schemas.PlannerOrderDue(
                    purchase_order_id=order_id,
                    supplier_id=lines[0].supplier_id,
                    expected_date=lines[0].expected_date,
                    arrival_date=lines[0].arrival_date,
                    overdue=lines[0].overdue,
                    total_quantity=sum((item.quantity for item in lines), ZERO),
                    lines=[
                        schemas.PlannerOrderLine(
                            product_id=item.product_id,
                            sku=item.sku,
                            product_name=item.product_name,
                            quantity=item.quantity,
                            unit_cost=item.unit_cost,
                            expiry_date=item.expiry_date,
                        )
                        for item in lines
                    ],
                )
            )
            day_cards[day].append(_receive_order_card(lines))

    days_out: list[schemas.PlannerDay] = []
    uncovered_by_day: dict[date, Decimal] = {}
    for day in projection_days:
        if day < board_start:
            continue
        states = [plan.days[day] for plan in plans]
        cards = sorted(
            day_cards.get(day, []),
            key=lambda card: (CARD_ORDER.get(card.kind, 9), card.product_sku, card.summary),
        )
        value_at_risk = sum((row.at_risk_cost for row in states), ZERO)
        expected_waste = sum((row.expired_cost for row in states), ZERO)
        if day == board_start:
            expected_waste += _cost(
                sum(
                    (
                        batch.quantity * batch.unit_cost
                        for plan in plans
                        for batch in plan.expired_before
                    ),
                    ZERO,
                )
            )
        unmet = sum((row.unmet_demand for row in states), ZERO)
        # Demand that no task on the board answers. A buy or bake task covers the
        # shortage it belongs to, so only the rest counts as residual risk.
        uncovered_unmet = sum(
            (
                row.unmet_demand
                for plan, row in zip(plans, states)
                if plan.product.id not in replenished
            ),
            ZERO,
        )
        demand = sum((row.expected_sales + row.unmet_demand for row in states), ZERO)
        ending = sum((row.ending_stock for row in states), ZERO)
        if unmet > 0:
            stockout_risk = "high"
        elif demand > 0 and ending <= demand * Decimal("0.1"):
            stockout_risk = "medium"
        else:
            stockout_risk = "low"
        if any(card.kind == "WRITE_OFF" for card in cards) or uncovered_unmet > 0:
            risk_level = "risky"
        elif cards:
            risk_level = "busy"
        else:
            risk_level = "calm"
        uncovered_by_day[day] = uncovered_unmet
        days_out.append(
            schemas.PlannerDay(
                date=day,
                weekday=day.strftime("%A"),
                headline=_headline(cards),
                risk_level=risk_level,
                kpis=schemas.PlannerDayKpis(
                    value_at_risk=value_at_risk,
                    expected_waste=expected_waste,
                    stockout_risk=stockout_risk,
                ),
                cards=cards,
                orders_due=orders_due.get(day, []),
                projection=schemas.PlannerProjection(
                    starting_stock=sum((row.starting_stock for row in states), ZERO),
                    arrivals=sum((row.arrivals for row in states), ZERO),
                    expected_sales=sum((row.expected_sales for row in states), ZERO),
                    unmet_demand=unmet,
                    ending_stock=ending,
                    expired_quantity=sum((row.expired_quantity for row in states), ZERO),
                ),
            )
        )

    for plan in plans:
        if not any(
            card.product_id == plan.product.id for day in days_out for card in day.cards
        ):
            days_out[0].cards.append(
                _card(
                    "HOLD",
                    "info",
                    plan=plan,
                    quantity=ZERO,
                    summary=f"No action needed for {plan.name} this week.",
                    why=[
                        "Stock covers the forecast demand for the week.",
                        "No expiry, order, or replenishment action is projected.",
                        "Revisit the plan if sales or orders change.",
                    ],
                    confidence=plan.confidence,
                    expiry_risk="healthy",
                    impact="Nothing to do.",
                    calculation={},
                )
            )
    for day in days_out:
        day.cards.sort(
            key=lambda card: (CARD_ORDER.get(card.kind, 9), card.product_sku, card.summary)
        )

    total_waste = _cost(sum((day.kpis.expected_waste for day in days_out), ZERO))
    total_at_risk = _cost(sum((plan.expiring_this_week_cost for plan in plans), ZERO))
    rescued_cost = _cost(
        sum(
            (
                plan.days[day.date].rescued_cost
                for plan in plans
                for day in days_out
            ),
            ZERO,
        )
    )
    stockout_days = sum(1 for day in days_out if day.kpis.stockout_risk == "high")
    waste_free_days = sum(1 for day in days_out if day.kpis.expected_waste == 0)
    # A day is covered when the plan leaves nothing to write off and no shortage
    # that no task answers, so the progress bar measures the plan, not the forecast.
    clean_days = sum(
        1
        for day in days_out
        if not any(card.kind == "WRITE_OFF" for card in day.cards)
        and uncovered_by_day.get(day.date, ZERO) <= 0
    )
    card_count = sum(len(day.cards) for day in days_out)

    return schemas.PlannerWeek(
        as_of=as_of,
        start_date=board_start,
        end_date=board_end,
        day_count=len(days_out),
        mode="forecast",
        engine=settings.forecast_engine,
        generated_at=utc_now(),
        days=days_out,
        badges=_badges(days_out, waste_free_days, stockout_days, clean_days, rescued_cost),
        weekly_summary=schemas.PlannerWeeklySummary(
            days=len(days_out),
            cards=card_count,
            cost_at_risk=total_at_risk,
            expected_waste=total_waste,
            estimated_cost_avoided=rescued_cost,
            stockout_days=stockout_days,
            waste_free_days=waste_free_days,
            plan_coverage_days=clean_days,
            quest_progress=round(clean_days / len(days_out), 4) if days_out else 0.0,
        ),
        assumptions=ASSUMPTIONS,
    )
