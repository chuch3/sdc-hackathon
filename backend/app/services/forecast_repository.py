from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import Settings
from app.services import inventory
from app.services.timeutil import business_date


def forecast_root(settings: Settings) -> Path:
    if settings.forecast_package_root:
        return Path(settings.forecast_package_root).resolve()
    return Path(__file__).resolve().parents[3]


def import_forecast(settings: Settings):
    root = forecast_root(settings)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from forecast import contracts, pipeline, policies, repository

    return contracts, pipeline, policies, repository


def build_pipeline(db: Session, as_of: date, settings: Settings):
    """Build the forecast pipeline for a read-only session."""
    contracts, pipeline_module, policies, repository_module = import_forecast(settings)
    repository = SQLAlchemyForecastRepository(db, as_of, settings)
    if settings.forecast_engine.lower() == "ml":
        from forecast.ml import MLForecaster, load_config

        config = load_config(settings.forecast_ml_config)
        checkpoint = settings.forecast_model_path
        if checkpoint is None:
            checkpoint = str(forecast_root(settings) / "forecast" / "artifacts" / "model.pt")
        forecaster = MLForecaster.from_config(config, checkpoint_path=checkpoint)
        return pipeline_module.ForecastPipeline(repository=repository, forecaster=forecaster)
    return pipeline_module.ForecastPipeline(repository=repository)


class SQLAlchemyForecastRepository:
    """Read-only adapter from M1/M2 tables to the forecast package contracts."""

    def __init__(self, db: Session, as_of: date, settings: Settings) -> None:
        self.db = db
        self.as_of = as_of
        self.settings = settings
        self.contracts, self.pipeline_module, self.policies, self.repository_module = (
            import_forecast(settings)
        )
        self.thresholds = inventory.expiry_thresholds(db)
        self._products = None

    def products(self):
        if self._products is not None:
            return self._products
        contracts = self.contracts
        bread_profiles = {
            profile.product_id: profile
            for profile in self.db.scalars(select(models.BreadProfile))
        }
        products = []
        for row in self.db.scalars(
            select(models.Product).where(models.Product.active.is_(True)).order_by(models.Product.id)
        ):
            profile = bread_profiles.get(row.id)
            products.append(
                contracts.Product(
                    sku=row.sku,
                    name=row.name,
                    category=row.category,
                    domain=contracts.Domain(row.domain),
                    unit=row.unit,
                    shelf_life_days=row.shelf_life_days,
                    lead_time_days=row.lead_time_days,
                    review_period_days=row.review_period_days,
                    moq=max(1, math.ceil(float(row.moq))),
                    case_size=max(1, math.ceil(float(row.case_size))),
                    safety_stock_days=float(row.safety_stock_days),
                    service_level=float(row.service_level),
                    weekday_factors={
                        int(key): float(value)
                        for key, value in (profile.weekday_factors if profile else {}).items()
                    },
                    daypart_shares={
                        str(key): float(value)
                        for key, value in (profile.daypart_shares if profile else {}).items()
                    },
                    near_expiry_threshold_days=inventory.threshold_for(
                        self.db, row.category, self.thresholds
                    ),
                )
            )
        self._products = tuple(products)
        return self._products

    def sales_history(self):
        contracts = self.contracts
        products = {product.sku: product for product in self.products()}
        ids = {
            row.id: row.sku
            for row in self.db.scalars(select(models.Product))
            if row.sku in products
        }
        if not ids:
            return ()
        start = self.as_of - timedelta(days=max(1, self.settings.forecast_history_days))
        movements = self.db.scalars(
            select(models.StockMovement)
            .where(
                models.StockMovement.product_id.in_(ids),
                models.StockMovement.movement_type == "SALE",
                models.StockMovement.occurred_at >= _utc_start(start, self.settings),
            )
            .order_by(models.StockMovement.occurred_at, models.StockMovement.id)
        )
        grouped: dict[tuple[int, date, str | None], float] = {}
        for movement in movements:
            day = business_date(movement.occurred_at, self.settings)
            key = (movement.product_id, day, movement.daypart)
            grouped[key] = grouped.get(key, 0.0) + float(-movement.quantity_delta)

        censored_days = {
            (event.product_id, event.business_date)
            for event in self.db.scalars(
                select(models.StockoutEvent).where(
                    models.StockoutEvent.product_id.in_(ids),
                    models.StockoutEvent.business_date >= start,
                    models.StockoutEvent.business_date <= self.as_of,
                )
            )
        }
        observations = []
        seen_days: set[tuple[int, date]] = set()
        for (product_id, day, daypart), quantity in grouped.items():
            observations.append(
                contracts.SalesObservation(
                    product_sku=ids[product_id],
                    business_date=day,
                    quantity=quantity,
                    daypart=daypart,
                    is_stockout_censored=(product_id, day) in censored_days,
                )
            )
            seen_days.add((product_id, day))
        for product_id, day in censored_days:
            if (product_id, day) in seen_days:
                continue
            observations.append(
                contracts.SalesObservation(
                    product_sku=ids[product_id],
                    business_date=day,
                    quantity=0.0,
                    is_stockout_censored=True,
                )
            )
        observations.sort(key=lambda item: (item.business_date, item.product_sku, item.daypart or ""))
        return tuple(observations)

    def inventory(self):
        contracts = self.contracts
        positions = []
        for product in self.products():
            row = self.db.scalar(select(models.Product).where(models.Product.sku == product.sku))
            saleable = inventory.saleable_on_hand(self.db, row.id, self.as_of)
            on_order, _ = inventory.on_order_totals(self.db, row.id, self.as_of)
            positions.append(
                contracts.InventoryPosition(
                    product_sku=product.sku,
                    saleable_on_hand=float(saleable),
                    on_order=float(on_order),
                    remaining_shelf_life_days=inventory.remaining_shelf_life_days(
                        self.db, row.id, self.as_of
                    ),
                )
            )
        return tuple(positions)

    def overrides(self):
        contracts = self.contracts
        return tuple(
            contracts.CalendarOverride(
                business_date=row.holiday_date,
                multiplier=float(row.demand_multiplier),
                product_sku=None,
                kind="holiday",
            )
            for row in self.db.scalars(
                select(models.HolidayCalendar).order_by(models.HolidayCalendar.holiday_date)
            )
        )


def _utc_start(day: date, settings: Settings):
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    local = datetime.combine(day, datetime.min.time(), tzinfo=ZoneInfo(settings.business_timezone))
    return local.astimezone(timezone.utc)
