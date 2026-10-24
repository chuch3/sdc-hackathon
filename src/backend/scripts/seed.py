"""Create fictional, repeatable demo records without replacing existing data.

The fixture models a small bakehouse with a short grocery counter: bakery
products that are baked each morning, plus dairy, produce and pantry lines
that arrive from suppliers. Every quantity change is written to the stock
ledger so each batch reconciles to its movements.

Nothing here is real data: names, quantities, prices and emissions factors
are fictional or explicitly labelled illustrative placeholders.
"""

import argparse
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from random import Random

from sqlalchemy import func, select

from app import models
from app.config import Settings
from app.db import build_engine, session_factory

HISTORY_DAYS = 42

SUPPLIERS = [
    ("Fictional Dairy Supplier", 2, "6", "0.960"),
    ("Fictional Produce Supplier", 1, "5", "0.930"),
    ("Fictional Bakery Supplier", 2, "4", "0.950"),
    ("Fictional Mill & Flour Company", 3, "10", "0.900"),
    ("Fictional Creamery Partner", 2, "8", "0.970"),
    ("Fictional Orchard Collective", 3, "12", "0.880"),
    ("Fictional Spice & Pantry Traders", 4, "6", "0.900"),
    ("Fictional Neighbourhood Market Stall", 1, "3", "0.920"),
]

# sku, name, category, unit, shelf life, storage, supplier index, allergens,
# domain, seasonal, lead time, moq, case size, safety stock days, base daily
# demand, weekend factor, max daily bake, daypart shares
PRODUCTS = [
    (
        "MILK-001",
        "Demo Fresh Milk",
        "dairy",
        "litre",
        7,
        "chilled",
        0,
        ["milk"],
        "generic",
        False,
        2,
        "6",
        6,
        "1.5",
        30,
        1.1,
        0,
        {},
    ),
    (
        "APPLE-001",
        "Demo Apples",
        "produce",
        "kg",
        10,
        "chilled",
        1,
        [],
        "generic",
        True,
        3,
        "12",
        6,
        "2",
        18,
        1.15,
        0,
        {},
    ),
    (
        "BREAD-001",
        "Demo Sourdough",
        "bakery",
        "loaf",
        3,
        "ambient",
        2,
        ["gluten"],
        "bakery",
        False,
        2,
        "6",
        6,
        "1",
        26,
        1.25,
        220,
        {"morning": 0.5, "midday": 0.3, "afternoon": 0.2},
    ),
    (
        "BUN-001",
        "Demo Butter Bun",
        "bakery",
        "piece",
        2,
        "ambient",
        2,
        ["gluten", "milk", "egg"],
        "bakery",
        False,
        2,
        "12",
        12,
        "1",
        34,
        1.2,
        260,
        {"morning": 0.55, "midday": 0.28, "afternoon": 0.17},
    ),
    (
        "BREAD-002",
        "Demo Walnut & Fig Sourdough",
        "bakery",
        "loaf",
        3,
        "ambient",
        3,
        ["gluten", "nuts"],
        "bakery",
        True,
        3,
        "6",
        6,
        "1",
        16,
        1.3,
        140,
        {"morning": 0.45, "midday": 0.32, "afternoon": 0.23},
    ),
    (
        "BUN-002",
        "Demo Cinnamon Morning Bun",
        "bakery",
        "piece",
        2,
        "ambient",
        2,
        ["gluten", "milk", "egg"],
        "bakery",
        False,
        2,
        "12",
        12,
        "1",
        22,
        1.15,
        180,
        {"morning": 0.6, "midday": 0.25, "afternoon": 0.15},
    ),
    (
        "CAKE-001",
        "Demo Cardamom Knot",
        "bakery",
        "piece",
        3,
        "ambient",
        2,
        ["gluten", "milk", "egg"],
        "bakery",
        False,
        2,
        "6",
        6,
        "1",
        14,
        1.35,
        120,
        {"morning": 0.4, "midday": 0.35, "afternoon": 0.25},
    ),
    (
        "BREAD-003",
        "Demo Seeded Country Rye",
        "bakery",
        "loaf",
        5,
        "ambient",
        3,
        ["gluten", "sesame"],
        "bakery",
        False,
        3,
        "6",
        6,
        "1.5",
        12,
        1.05,
        160,
        {"morning": 0.42, "midday": 0.33, "afternoon": 0.25},
    ),
    (
        "CREAM-001",
        "Demo Double Cream",
        "dairy",
        "litre",
        7,
        "chilled",
        4,
        ["milk"],
        "generic",
        False,
        2,
        "8",
        12,
        "1.5",
        16,
        1.1,
        0,
        {},
    ),
    (
        "YOG-001",
        "Demo Natural Yoghurt",
        "dairy",
        "tub",
        10,
        "chilled",
        4,
        ["milk"],
        "generic",
        False,
        2,
        "12",
        12,
        "2",
        20,
        1.05,
        0,
        {},
    ),
    (
        "BUTTER-001",
        "Demo Cultured Butter",
        "dairy",
        "block",
        14,
        "chilled",
        4,
        ["milk"],
        "generic",
        False,
        3,
        "10",
        10,
        "3",
        14,
        1.0,
        0,
        {},
    ),
    (
        "PEAR-001",
        "Demo Conference Pear",
        "produce",
        "kg",
        8,
        "chilled",
        5,
        [],
        "generic",
        True,
        3,
        "12",
        12,
        "2",
        15,
        1.1,
        0,
        {},
    ),
    (
        "PUMPKIN-001",
        "Demo Sugar Pumpkin",
        "produce",
        "kg",
        21,
        "ambient",
        5,
        [],
        "generic",
        True,
        4,
        "15",
        15,
        "3",
        9,
        1.2,
        0,
        {},
    ),
    (
        "HERB-001",
        "Demo Flat Parsley",
        "produce",
        "bunch",
        5,
        "chilled",
        1,
        [],
        "generic",
        False,
        1,
        "10",
        10,
        "1",
        11,
        1.0,
        0,
        {},
    ),
    (
        "FLOUR-001",
        "Demo Stoneground Bread Flour",
        "pantry",
        "kg",
        90,
        "ambient",
        3,
        ["gluten"],
        "generic",
        False,
        3,
        "25",
        25,
        "7",
        24,
        1.0,
        0,
        {},
    ),
    (
        "HONEY-001",
        "Demo Wildflower Honey",
        "pantry",
        "jar",
        365,
        "ambient",
        6,
        [],
        "generic",
        True,
        4,
        "6",
        12,
        "5",
        7,
        1.0,
        0,
        {},
    ),
]

# Open stock per product: (label, quantity, expiry offset in days, unit cost).
# Only a handful of lines are genuinely near expiry, the way a real shop looks
# on a Tuesday; the rest carry stock that still has shelf life.
OPEN_BATCHES = {
    "MILK-001": [("soon", "18", 1, "3.20"), ("later", "90", 5, "3.20")],
    "APPLE-001": [("soon", "14", 2, "4.10"), ("later", "27", 8, "4.10")],
    "BREAD-001": [("soon", "22", 0, "2.60"), ("later", "39", 2, "2.60")],
    "BUN-001": [("soon", "26", 0, "1.40"), ("later", "51", 1, "1.40")],
    "BREAD-002": [("soon", "12", 2, "4.80"), ("later", "24", 3, "4.80")],
    "BUN-002": [("soon", "20", 1, "1.60"), ("later", "33", 2, "1.60")],
    "CAKE-001": [("soon", "10", 1, "1.90"), ("later", "21", 3, "1.90")],
    "BREAD-003": [("soon", "9", 3, "3.30"), ("later", "18", 4, "3.30")],
    "CREAM-001": [("soon", "8", 3, "5.20"), ("later", "48", 5, "5.20")],
    "YOG-001": [("soon", "10", 4, "4.40"), ("later", "60", 8, "4.40")],
    "BUTTER-001": [("soon", "7", 7, "6.80"), ("later", "42", 12, "6.80")],
    "PEAR-001": [("soon", "11", 4, "5.60"), ("later", "45", 6, "5.60")],
    "PUMPKIN-001": [("soon", "16", 5, "3.10"), ("later", "24", 18, "3.10")],
    "HERB-001": [("soon", "9", 2, "1.20"), ("later", "16", 4, "1.20")],
    "FLOUR-001": [("soon", "30", 6, "1.80"), ("later", "72", 80, "1.80")],
    "HONEY-001": [("soon", "6", 8, "7.40"), ("later", "21", 300, "7.40")],
}

# Purchase orders: (supplier index, status, expected offset, lines)
# lines: (sku, quantity, unit cost, received quantity)
PURCHASE_ORDERS = [
    (
        0,
        "APPROVED",
        2,
        [("MILK-001", "48", "3.20", "0"), ("CREAM-001", "24", "5.20", "0")],
    ),
    (
        1,
        "APPROVED",
        1,
        [("APPLE-001", "30", "4.10", "0"), ("HERB-001", "20", "1.20", "0")],
    ),
    (
        3,
        "DRAFT",
        4,
        [("FLOUR-001", "75", "1.80", "0"), ("BREAD-003", "24", "3.30", "0")],
    ),
    (
        2,
        "APPROVED",
        -2,
        [("BUN-001", "60", "1.40", "0")],
    ),
    (
        5,
        "RECEIVED",
        -4,
        [("PEAR-001", "24", "5.60", "24"), ("PUMPKIN-001", "30", "3.10", "30")],
    ),
    (
        6,
        "CANCELLED",
        6,
        [("HONEY-001", "12", "7.40", "0")],
    ),
]

HOLIDAYS = [
    ("Fictional Founders' Day market", 3, "1.25"),
    ("Fictional Harvest Weekend", 6, "1.30"),
    ("Fictional Lantern Festival", 12, "1.15"),
    ("Fictional Winter Solstice Bake", 20, "1.20"),
    ("Fictional Founders' Day market (last year)", -30, "1.25"),
]

# Separate from holidays: these are shop-configured local trading events.
MARKET_DAYS = [
    ("Fictional Saturday farmers market", 2, "1.18", "Open the morning bake counter early."),
    ("Fictional neighbourhood night market", 9, "1.12", "Prepare smaller late-day batches."),
]

SEASONAL_INGREDIENTS = [
    ("Fictional Sugar Pumpkin", [10, 11, 12], "0.900", "0.950", True),
    ("Fictional Walnuts", [10, 11, 12], "0.850", "1.100", True),
    ("Fictional Figs", [9, 10, 11], "0.700", "1.250", False),
    ("Fictional Apples", [8, 9, 10, 11], "0.950", "0.900", True),
    ("Fictional Pears", [8, 9, 10], "0.800", "1.050", True),
    ("Fictional Cardamom", [9, 10, 11, 12], "0.750", "1.150", False),
    ("Fictional Cinnamon", [1, 2, 3, 4, 9, 10, 11, 12], "0.950", "0.880", False),
    ("Fictional Parsley", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "0.880", "0.950", True),
    ("Fictional Honeycomb", [5, 6, 7, 8], "0.600", "1.300", True),
    ("Fictional Orange Zest", [11, 12, 1, 2], "0.700", "1.200", False),
]

# category, kg CO2e per kg wasted, meals per kg donated, source note
SDG_FACTORS = [
    (
        "bakery",
        "2.2000",
        "3.0000",
        "ILLUSTRATIVE PLACEHOLDER: mid-range bakery emission intensity from published "
        "food-category life-cycle studies (Poore & Nemecek 2018). Replace with measured "
        "local values before reporting.",
    ),
    (
        "dairy",
        "3.1000",
        "4.0000",
        "ILLUSTRATIVE PLACEHOLDER: mid-range dairy emission intensity from published "
        "food-category life-cycle studies (Poore & Nemecek 2018). Replace with measured "
        "local values before reporting.",
    ),
    (
        "produce",
        "0.6000",
        "5.0000",
        "ILLUSTRATIVE PLACEHOLDER: mid-range produce emission intensity from published "
        "food-category life-cycle studies (Poore & Nemecek 2018). Replace with measured "
        "local values before reporting.",
    ),
    (
        "pantry",
        "1.4000",
        "6.0000",
        "ILLUSTRATIVE PLACEHOLDER: mid-range pantry emission intensity from published "
        "food-category life-cycle studies (Poore & Nemecek 2018). Replace with measured "
        "local values before reporting.",
    ),
]

# sku, business date offset, daypart, requested, available
STOCKOUTS = [
    ("BUN-001", -9, "morning", "12", "0"),
    ("BREAD-001", -16, "midday", "8", "0"),
    ("MILK-001", -23, "morning", "6", "0"),
]


def _movement(db, product_id, batch_id, kind, delta, when, reason, daypart=None, tag=""):
    db.add(
        models.StockMovement(
            product_id=product_id,
            batch_id=batch_id,
            movement_type=kind,
            quantity_delta=Decimal(delta),
            occurred_at=when,
            daypart=daypart,
            reason=reason,
            actor_name="Synthetic Seed",
            request_id=f"seed:{tag}:{kind}:{batch_id}:{when.isoformat()}",
        )
    )


def seed(database_url=None, as_of=None, include_history=True, history_days=HISTORY_DAYS):
    settings = Settings()
    today = as_of or settings.business_today()
    history_days = max(0, history_days) if include_history else 0
    engine = build_engine(database_url or settings.database_url)
    try:
        with session_factory(engine)() as db:
            if db.get(models.Setting, "demo_seed"):
                print("Demo data already loaded; nothing changed.")
                return
            if db.scalar(select(func.count()).select_from(models.Product)):
                raise SystemExit(
                    "Existing products found. Use a NEW demo database to load fixtures."
                )

            suppliers = []
            for name, lead_time, moq, reliability in SUPPLIERS:
                supplier = models.Supplier(
                    name=name,
                    lead_time_days=lead_time,
                    moq=Decimal(moq),
                    reliability=Decimal(reliability),
                )
                db.add(supplier)
                suppliers.append(supplier)
            db.flush()

            products = []
            profiles = []
            for spec in PRODUCTS:
                (
                    sku,
                    name,
                    category,
                    unit,
                    shelf_life,
                    storage,
                    supplier_index,
                    allergens,
                    domain,
                    seasonal,
                    lead_time,
                    moq,
                    case_size,
                    safety_days,
                    base_daily,
                    weekend_factor,
                    max_daily,
                    daypart_shares,
                ) = spec
                product = models.Product(
                    sku=sku,
                    name=name,
                    category=category,
                    unit=unit,
                    shelf_life_days=shelf_life,
                    storage_type=storage,
                    supplier_id=suppliers[supplier_index].id,
                    lead_time_days=lead_time,
                    moq=Decimal(moq),
                    case_size=case_size,
                    safety_stock_days=Decimal(safety_days),
                    allergens=allergens,
                    domain=domain,
                    seasonal=seasonal,
                )
                db.add(product)
                products.append(product)
                if domain == "bakery":
                    profiles.append(
                        (
                            product,
                            {str(day): (weekend_factor if day >= 5 else 1.0) for day in range(7)},
                            daypart_shares,
                            Decimal(max_daily),
                        )
                    )
            db.flush()

            def batch_with_receipt(product, code, quantity, received, expiry, cost="2.50"):
                batch = models.Batch(
                    product_id=product.id,
                    batch_code=code,
                    quantity_received=Decimal(quantity),
                    quantity_remaining=Decimal(quantity),
                    received_date=received,
                    baked_date=received if product.domain == "bakery" else None,
                    expiry_date=expiry,
                    unit_cost=Decimal(cost),
                    status="ACTIVE",
                )
                db.add(batch)
                db.flush()
                _movement(
                    db,
                    product.id,
                    batch.id,
                    "RECEIPT",
                    quantity,
                    datetime.combine(received, datetime.min.time(), tzinfo=timezone.utc),
                    "Fictional opening/production receipt",
                    tag="receipt",
                )
                return batch

            # Open stock: one batch near expiry and one that keeps longer.
            for product in products:
                for label, quantity, offset, cost in OPEN_BATCHES[product.sku]:
                    received = today - timedelta(
                        days=max(0, min(3, product.shelf_life_days - offset))
                    )
                    batch_with_receipt(
                        product,
                        f"DEMO-{product.sku}-{label}",
                        quantity,
                        received,
                        today + timedelta(days=offset),
                        cost,
                    )

            # A little trouble for the expiry view: expired and quarantined stock.
            expired = batch_with_receipt(
                products[2],
                "DEMO-BREAD-001-expired",
                "6",
                today - timedelta(days=4),
                today - timedelta(days=1),
                "2.60",
            )
            quarantined = batch_with_receipt(
                products[3],
                "DEMO-BUN-001-quarantined",
                "5",
                today - timedelta(days=1),
                today + timedelta(days=1),
                "1.40",
            )
            quarantined.status = "QUARANTINED"
            expired.quantity_remaining = Decimal("6")

            # Daily history so the baseline forecaster has something to learn from.
            rng = Random(42)
            by_sku = {product.sku: product for product in products}
            for days_ago in range(history_days, 0, -1):
                business_day = today - timedelta(days=days_ago)
                for product in products:
                    spec = next(item for item in PRODUCTS if item[0] == product.sku)
                    base_daily = spec[14]
                    weekend_factor = spec[15]
                    factor = weekend_factor if business_day.weekday() >= 5 else 1.0
                    sold = max(1, round(base_daily * factor + rng.randint(-3, 3)))
                    wasted = 0 if rng.random() < 0.82 else rng.randint(1, 3)
                    donated = 0
                    if rng.random() < 0.1:
                        donated = rng.randint(1, 2)
                    quantity = sold + wasted + donated
                    code = f"HIST-{product.sku}-{business_day.isoformat()}"
                    batch = batch_with_receipt(
                        product,
                        code,
                        str(quantity),
                        business_day,
                        business_day + timedelta(days=min(product.shelf_life_days, 3)),
                        "2.50",
                    )
                    batch.quantity_remaining = Decimal("0")
                    batch.status = "CLOSED"
                    morning = max(1, round(sold * 0.6))
                    midday = sold - morning
                    for kind, amount, hour, daypart in [
                        ("SALE", morning, 5, "morning"),
                        ("SALE", midday, 11, "midday"),
                        ("WASTE", wasted, 19, "evening"),
                        ("DONATION", donated, 16, "afternoon"),
                    ]:
                        if not amount:
                            continue
                        _movement(
                            db,
                            product.id,
                            batch.id,
                            kind,
                            str(-amount),
                            datetime(
                                business_day.year,
                                business_day.month,
                                business_day.day,
                                hour,
                                tzinfo=timezone.utc,
                            ),
                            "Team-created synthetic history",
                            daypart=daypart,
                            tag=kind.lower(),
                        )

            # Purchase orders in every workflow state.
            for supplier_index, status, offset, lines in PURCHASE_ORDERS:
                expected = today + timedelta(days=offset)
                order = models.PurchaseOrder(
                    supplier_id=suppliers[supplier_index].id,
                    status=status,
                    expected_date=expected,
                )
                db.add(order)
                db.flush()
                for sku, quantity, cost, received in lines:
                    product = by_sku[sku]
                    line = models.PurchaseOrderLine(
                        purchase_order_id=order.id,
                        product_id=product.id,
                        quantity=Decimal(quantity),
                        received_quantity=Decimal(received),
                        unit_cost=Decimal(cost),
                    )
                    db.add(line)
                    db.flush()
                    if status == "RECEIVED":
                        batch = batch_with_receipt(
                            product,
                            f"PO-{order.id}-{sku}",
                            received,
                            expected,
                            expected + timedelta(days=min(product.shelf_life_days, 4)),
                            cost,
                        )
                        _movement(
                            db,
                            product.id,
                            batch.id,
                            "SALE",
                            str(-Decimal(received)),
                            datetime.combine(expected, time(hour=7), tzinfo=timezone.utc),
                            "Fictional delivery sold through the counter",
                            daypart="morning",
                            tag="po-sale",
                        )
                        batch.quantity_remaining = Decimal("0")
                        batch.status = "CLOSED"
                if status in {"APPROVED", "RECEIVED"}:
                    order.approved_by = "Demo Owner"
                    order.approved_at = datetime.combine(
                        today, datetime.min.time(), tzinfo=timezone.utc
                    )

            # Stockout markers so censored demand is visible in the forecast history.
            for sku, offset, daypart, requested, available in STOCKOUTS:
                product = by_sku[sku]
                db.add(
                    models.StockoutEvent(
                        product_id=product.id,
                        business_date=today + timedelta(days=offset),
                        daypart=daypart,
                        requested_quantity=Decimal(requested),
                        available_quantity=Decimal(available),
                        source="SALE_REJECTED",
                        note="Fictional empty-shelf moment",
                    )
                )

            for product, weekday_factors, daypart_shares, max_daily in profiles:
                db.add(
                    models.BreadProfile(
                        product_id=product.id,
                        weekday_factors=weekday_factors,
                        daypart_shares=daypart_shares,
                        max_daily_quantity=max_daily,
                    )
                )

            for name, months, availability, price_index, local in SEASONAL_INGREDIENTS:
                db.add(
                    models.SeasonalIngredient(
                        name=name,
                        months_available=months,
                        availability_score=Decimal(availability),
                        price_index=Decimal(price_index),
                        local=local,
                    )
                )

            for label, offset, multiplier in HOLIDAYS:
                db.add(
                    models.HolidayCalendar(
                        holiday_date=today + timedelta(days=offset),
                        label=label,
                        demand_multiplier=Decimal(multiplier),
                    )
                )

            for label, offset, multiplier, note in MARKET_DAYS:
                db.add(
                    models.MarketDay(
                        market_date=today + timedelta(days=offset),
                        label=label,
                        demand_multiplier=Decimal(multiplier),
                        note=note,
                    )
                )

            # A finished bake plan yesterday and a draft for today.
            for product in products:
                if product.domain != "bakery":
                    continue
                for daypart, share in (("morning", 0.5), ("midday", 0.3)):
                    db.add(
                        models.ProductionPlan(
                            plan_date=today - timedelta(days=1),
                            product_id=product.id,
                            daypart=daypart,
                            planned_quantity=Decimal("24"),
                            actual_baked=Decimal("24"),
                            sold=Decimal("21"),
                            discarded=Decimal("3"),
                            status="DONE",
                            approved_by="Demo Owner",
                            approved_at=datetime.combine(
                                today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
                            ),
                        )
                    )

            db.add(
                models.Setting(
                    key="expiry_threshold_days",
                    value={"bakery": 1, "dairy": 3, "produce": 2, "meat": 1, "pantry": 5},
                )
            )
            db.add(
                models.Setting(
                    key="demo_seed",
                    value={
                        "as_of": today.isoformat(),
                        "synthetic": True,
                        "products": len(products),
                        "history_days": history_days,
                    },
                )
            )
            for category, co2e, meals, note in SDG_FACTORS:
                db.add(
                    models.SDGFactor(
                        category=category,
                        kg_co2e_per_kg_waste=Decimal(co2e),
                        meals_per_kg_donated=Decimal(meals),
                        source_note=note,
                    )
                )
            db.commit()
            print(
                f"Seed complete for {today}: {len(suppliers)} suppliers, {len(products)} products, "
                f"{history_days} days of history, "
                f"{len(PURCHASE_ORDERS)} purchase orders."
            )
            print("All records are fictional. SDG factors are illustrative placeholders.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=date.fromisoformat, help="Optional YYYY-MM-DD seed date")
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="Create products, opening stock, and orders without sales history.",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=HISTORY_DAYS,
        help="Number of synthetic sales-history days to create.",
    )
    args = parser.parse_args()
    seed(
        as_of=args.as_of,
        include_history=not args.skip_history,
        history_days=args.history_days,
    )
