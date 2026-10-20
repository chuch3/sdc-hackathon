"""Create fictional, repeatable demo records without replacing existing data."""

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from random import Random

from sqlalchemy import func, select

from app import models
from app.config import Settings
from app.db import build_engine, session_factory


def seed(database_url=None, as_of=None):
    settings = Settings()
    today = as_of or settings.business_today()
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
            suppliers = [
                models.Supplier(name=name)
                for name in [
                    "Fictional Dairy Supplier",
                    "Fictional Produce Supplier",
                    "Fictional Bakery Supplier",
                ]
            ]
            db.add_all(suppliers)
            db.flush()
            product_specs = [
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
                ),
                ("APPLE-001", "Demo Apples", "produce", "kg", 10, "chilled", 1, [], "generic"),
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
                ),
            ]
            products = []
            for (
                sku,
                name,
                category,
                unit,
                shelf,
                storage,
                supplier,
                allergens,
                domain,
            ) in product_specs:
                product = models.Product(
                    sku=sku,
                    name=name,
                    category=category,
                    unit=unit,
                    shelf_life_days=shelf,
                    storage_type=storage,
                    supplier_id=suppliers[supplier].id,
                    allergens=allergens,
                    domain=domain,
                )
                db.add(product)
                products.append(product)
            db.flush()

            def batch_with_receipt(product, code, quantity, received, expiry, status="ACTIVE"):
                batch = models.Batch(
                    product_id=product.id,
                    batch_code=code,
                    quantity_received=Decimal(quantity),
                    quantity_remaining=Decimal(quantity),
                    received_date=received,
                    baked_date=received if product.domain == "bakery" else None,
                    expiry_date=expiry,
                    unit_cost=Decimal("2.50"),
                    status=status,
                )
                db.add(batch)
                db.flush()
                db.add(
                    models.StockMovement(
                        product_id=product.id,
                        batch_id=batch.id,
                        movement_type="RECEIPT",
                        quantity_delta=Decimal(quantity),
                        occurred_at=datetime.combine(
                            received, datetime.min.time(), tzinfo=timezone.utc
                        ),
                        reason="Fictional opening/production receipt",
                        actor_name="Synthetic Seed",
                        request_id=f"seed:receipt:{code}",
                    )
                )
                return batch

            for index, product in enumerate(products):
                for label, days, quantity in [("soon", 0, "12"), ("later", 5, "25")]:
                    expiry_offset = min(days, product.shelf_life_days)
                    age = min(3, product.shelf_life_days - expiry_offset)
                    batch_with_receipt(
                        product,
                        f"DEMO-{index}-{label}",
                        quantity,
                        today - timedelta(days=age),
                        today + timedelta(days=expiry_offset),
                    )
            batch_with_receipt(
                products[0],
                "DEMO-expired",
                "5",
                today - timedelta(days=6),
                today - timedelta(days=1),
            )
            batch_with_receipt(
                products[2],
                "DEMO-quarantined",
                "4",
                today - timedelta(days=1),
                today + timedelta(days=1),
                "QUARANTINED",
            )

            # A small fictional history gives M3 a starting dataset, not a forecast model.
            rng = Random(42)
            for days_ago in range(35, 0, -1):
                business_day = today - timedelta(days=days_ago)
                for product in [products[0], products[2]]:
                    sold = 20 + rng.randint(-4, 4) + (6 if business_day.weekday() >= 5 else 0)
                    wasted = rng.randint(0, 3)
                    batch = batch_with_receipt(
                        product,
                        f"HIST-{product.sku}-{business_day.isoformat()}",
                        str(sold + wasted),
                        business_day,
                        business_day + timedelta(days=1),
                    )
                    batch.quantity_remaining, batch.status = Decimal("0"), "CLOSED"
                    for kind, amount, hour in [("SALE", sold, 4), ("WASTE", wasted, 10)]:
                        if amount:
                            db.add(
                                models.StockMovement(
                                    product_id=product.id,
                                    batch_id=batch.id,
                                    movement_type=kind,
                                    quantity_delta=Decimal(-amount),
                                    occurred_at=datetime(
                                        business_day.year,
                                        business_day.month,
                                        business_day.day,
                                        hour,
                                        tzinfo=timezone.utc,
                                    ),
                                    daypart="midday" if kind == "SALE" else "evening",
                                    reason="Team-created synthetic history",
                                    actor_name="Synthetic Seed",
                                    request_id=f"seed:{kind}:{batch.batch_code}",
                                )
                            )
            db.add(
                models.BreadProfile(
                    product_id=products[2].id,
                    weekday_factors={str(day): (1.2 if day >= 5 else 1.0) for day in range(7)},
                    daypart_shares={"morning": 0.5, "midday": 0.3, "afternoon": 0.2},
                    max_daily_quantity=Decimal("200"),
                )
            )
            db.add(
                models.SeasonalIngredient(
                    name="Fictional Demo Fruit",
                    months_available=[10, 11],
                    availability_score=Decimal("0.8"),
                    price_index=Decimal("1.0"),
                    local=True,
                )
            )
            db.add(
                models.HolidayCalendar(
                    holiday_date=today + timedelta(days=7),
                    label="Fictional demo event (not an official holiday)",
                    demand_multiplier=Decimal("1.15"),
                )
            )
            db.add(
                models.Setting(
                    key="expiry_threshold_days",
                    value={"bakery": 1, "dairy": 3, "produce": 2, "meat": 1},
                )
            )
            db.add(
                models.Setting(
                    key="demo_seed", value={"as_of": today.isoformat(), "synthetic": True}
                )
            )
            for category in ["bakery", "dairy", "produce"]:
                db.add(
                    models.SDGFactor(
                        category=category,
                        kg_co2e_per_kg_waste=Decimal("0"),
                        meals_per_kg_donated=Decimal("0"),
                        source_note="PLACEHOLDER ONLY: M3 must supply documented factors before reporting",
                    )
                )
            db.commit()
            print(
                f"Seed complete for {today}: 3 suppliers, 4 products, 80 batches, 35 days history."
            )
            print("All records are fictional. SDG factors are zero-valued placeholders.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=date.fromisoformat, help="Optional YYYY-MM-DD seed date")
    args = parser.parse_args()
    seed(as_of=args.as_of)
