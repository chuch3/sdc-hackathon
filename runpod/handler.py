"""RunPod serverless handler for the FreshStock quantile demand model.

The handler loads the locally trained forecast checkpoint and exposes it as a
synchronous RunPod endpoint. It returns q10/q50/q90 demand predictions for one
product and falls back to the rule-based baseline forecast when the checkpoint
is missing, the SKU is unseen, or the supplied history is too short/stale.

Example input::

    {
      "input": {
        "product": {
          "sku": "BREAD-001",
          "name": "Demo Sourdough",
          "category": "bakery",
          "domain": "bakery",
          "unit": "loaf",
          "shelf_life_days": 3,
          "lead_time_days": 2,
          "moq": 6,
          "case_size": 6
        },
        "as_of_date": "2026-10-24",
        "horizon_days": 3,
        "sales_history": [
          {"business_date": "2026-10-01", "quantity": 28},
          {"business_date": "2026-10-02", "quantity": 31}
        ],
        "overrides": [
          {"business_date": "2026-10-25", "multiplier": 1.25, "kind": "holiday"}
        ]
      }
    }

A compact history is also accepted as either a mapping of
``{"YYYY-MM-DD": quantity}`` or a list of daily quantity numbers.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (REPO_ROOT, REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import runpod
from forecast.contracts import (
    CalendarOverride,
    Domain,
    ForecastContext,
    ForecastRequest,
    ForecastResult,
    Product,
    ReasonCode,
    SalesObservation,
)
from forecast.ml.forecaster import MLForecaster

LOGGER = logging.getLogger("freshstock.runpod")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

DEFAULT_CHECKPOINT = REPO_ROOT / "src" / "forecast" / "artifacts" / "model.pt"
_FORECASTER: MLForecaster | None = None
_FORECASTER_LOCK = threading.Lock()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(float(value))


def _parse_date(value: Any, default: date | None = None) -> date | None:
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _parse_bool(value: Any, default: bool = False) -> bool:
    return _as_bool(value, default)


def _checkpoint_path() -> Path:
    configured = os.getenv("MODEL_PATH") or os.getenv("FORECAST_MODEL_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_CHECKPOINT


def _device() -> str:
    requested = os.getenv("DEVICE", "auto").strip().lower()
    if requested and requested != "auto":
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _get_forecaster() -> MLForecaster:
    global _FORECASTER
    if _FORECASTER is None:
        with _FORECASTER_LOCK:
            if _FORECASTER is None:
                checkpoint = _checkpoint_path()
                device = _device()
                LOGGER.info("Loading forecast model from %s on %s", checkpoint, device)
                _FORECASTER = MLForecaster(checkpoint, device=device)
    return _FORECASTER


def _parse_product(payload: Mapping[str, Any], fallback_sku: str) -> Product:
    sku = str(payload.get("sku") or payload.get("product_id") or fallback_sku).strip()
    if not sku:
        raise ValueError("product.sku or input.product_id is required")

    raw_domain = str(payload.get("domain", "generic")).strip().lower()
    domain = Domain.BAKERY if raw_domain == "bakery" else Domain.GENERIC

    weekday_factors = {
        int(key): float(value)
        for key, value in (payload.get("weekday_factors") or {}).items()
    }
    daypart_shares = {
        str(key): float(value)
        for key, value in (payload.get("daypart_shares") or {}).items()
    }

    return Product(
        sku=sku,
        name=str(payload.get("name") or sku),
        category=str(payload.get("category") or "generic"),
        domain=domain,
        unit=str(payload.get("unit") or "unit"),
        shelf_life_days=max(1, _as_int(payload.get("shelf_life_days"), 3)),
        lead_time_days=max(0, _as_int(payload.get("lead_time_days"), 1)),
        review_period_days=max(1, _as_int(payload.get("review_period_days"), 1)),
        moq=max(1, _as_int(payload.get("moq"), 1)),
        case_size=max(1, _as_int(payload.get("case_size"), 1)),
        safety_stock_days=max(0.0, _as_float(payload.get("safety_stock_days"), 1.0)),
        service_level=_as_float(payload.get("service_level"), 0.95),
        weekday_factors=weekday_factors,
        daypart_shares=daypart_shares,
        near_expiry_threshold_days=max(
            0, _as_int(payload.get("near_expiry_threshold_days"), 2)
        ),
    )


def _history_from_mapping(
    product_sku: str,
    raw: Mapping[Any, Any],
    default_daypart: str | None,
) -> list[SalesObservation]:
    observations: list[SalesObservation] = []
    for day_value, quantity_value in raw.items():
        if isinstance(quantity_value, Mapping):
            quantity = _as_float(
                quantity_value.get("quantity", quantity_value.get("sold")),
            )
            censored = _parse_bool(
                quantity_value.get("is_stockout_censored")
                or quantity_value.get("censored")
            )
            daypart = quantity_value.get("daypart") or default_daypart
        else:
            quantity = _as_float(quantity_value)
            censored = False
            daypart = default_daypart
        day = _parse_date(day_value)
        if day is None:
            continue
        observations.append(
            SalesObservation(
                product_sku=product_sku,
                business_date=day,
                quantity=quantity,
                daypart=str(daypart) if daypart else None,
                is_stockout_censored=censored,
            )
        )
    return observations


def _history_from_sequence(
    product_sku: str,
    raw: Sequence[Any],
    default_daypart: str | None,
    anchor: date,
) -> list[SalesObservation]:
    observations: list[SalesObservation] = []
    numeric_values = [item for item in raw if isinstance(item, (int, float))]
    if numeric_values and len(numeric_values) == len(raw):
        start = anchor - timedelta(days=len(numeric_values) - 1)
        for offset, quantity in enumerate(numeric_values):
            observations.append(
                SalesObservation(
                    product_sku=product_sku,
                    business_date=start + timedelta(days=offset),
                    quantity=float(quantity),
                    daypart=default_daypart,
                )
            )
        return observations

    for item in raw:
        if isinstance(item, Mapping):
            day = _parse_date(
                item.get("business_date") or item.get("date") or item.get("day")
            )
            if day is None:
                continue
            quantity = _as_float(
                item.get("quantity", item.get("sold", item.get("demand")))
            )
            censored = _parse_bool(
                item.get("is_stockout_censored") or item.get("censored")
            )
            daypart = item.get("daypart") or default_daypart
            observations.append(
                SalesObservation(
                    product_sku=product_sku,
                    business_date=day,
                    quantity=quantity,
                    daypart=str(daypart) if daypart else None,
                    is_stockout_censored=censored,
                )
            )
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            if len(item) < 2:
                continue
            day = _parse_date(item[0])
            if day is None:
                continue
            observations.append(
                SalesObservation(
                    product_sku=product_sku,
                    business_date=day,
                    quantity=_as_float(item[1]),
                    daypart=default_daypart,
                )
            )
    return observations


def _parse_history(
    payload: Mapping[str, Any],
    product_sku: str,
    default_daypart: str | None,
    anchor: date,
) -> list[SalesObservation]:
    raw = payload.get("sales_history", payload.get("history", []))
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        return _history_from_mapping(product_sku, raw, default_daypart)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return _history_from_sequence(product_sku, raw, default_daypart, anchor)
    raise ValueError("sales_history must be a list or an object")


def _parse_overrides(payload: Mapping[str, Any]) -> tuple[CalendarOverride, ...]:
    raw = payload.get("overrides", payload.get("calendar_overrides", []))
    if not raw:
        return ()
    if isinstance(raw, Mapping):
        raw = [
            {"business_date": key, "multiplier": value}
            for key, value in raw.items()
        ]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("overrides must be a list or an object")

    overrides: list[CalendarOverride] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        day = _parse_date(
            item.get("business_date") or item.get("date") or item.get("day")
        )
        if day is None:
            continue
        overrides.append(
            CalendarOverride(
                business_date=day,
                multiplier=_as_float(
                    item.get("multiplier", item.get("factor")), 1.0
                ),
                product_sku=item.get("product_sku") or item.get("sku"),
                kind=str(item.get("kind") or "holiday"),
            )
        )
    return tuple(overrides)


def _serialize_result(result: ForecastResult) -> dict[str, Any]:
    reason_codes = [code.value for code in result.reason_codes]
    fallback = ReasonCode.ML_FALLBACK_BASELINE.value in reason_codes
    return {
        "product_id": result.product_sku,
        "as_of_date": result.as_of_date.isoformat(),
        "horizon_days": result.horizon_days,
        "engine": "baseline" if fallback else "ml",
        "fallback": fallback,
        "model_name": result.model_name,
        "model_version": result.model_version,
        "actionable": result.actionable,
        "confidence": result.confidence.value,
        "total": {
            "quantity": result.total_quantity,
            "lower": result.total_lower,
            "upper": result.total_upper,
        },
        "by_day": [
            {
                "date": item.forecast_date.isoformat(),
                "q10": item.lower,
                "q50": item.quantity,
                "q90": item.upper,
                "daypart": item.daypart,
            }
            for item in result.daily
        ],
        "error_std": result.error_std,
        "reason_codes": reason_codes,
        "why": list(result.why),
        "data_quality": _jsonable(asdict(result.data_quality)),
        "forecast_run_id": result.forecast_run_id,
        "input_snapshot_id": result.input_snapshot_id,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _forecast(payload: Mapping[str, Any]) -> dict[str, Any]:
    product_payload = payload.get("product") or {}
    if not isinstance(product_payload, Mapping):
        raise ValueError("product must be an object")
    fallback_sku = str(payload.get("sku") or payload.get("product_id") or "")
    product = _parse_product(product_payload, fallback_sku)

    daypart_value = payload.get("daypart")
    daypart = str(daypart_value) if daypart_value else None

    anchor = _parse_date(
        payload.get("as_of_date") or payload.get("as_of"),
        date.today(),
    )
    assert anchor is not None
    observations = _parse_history(payload, product.sku, daypart, anchor)
    if observations and not (
        payload.get("as_of_date") or payload.get("as_of")
    ):
        anchor = max(item.business_date for item in observations)
    history = tuple(
        item for item in observations if item.business_date <= anchor
    )
    overrides = _parse_overrides(payload)

    horizon_days = max(1, min(_as_int(payload.get("horizon_days"), 1), 365))
    request = ForecastRequest(
        product_sku=product.sku,
        as_of_date=anchor,
        horizon_days=horizon_days,
        daypart=daypart,
        forecast_run_id=payload.get("request_id"),
        input_snapshot_id=payload.get("input_snapshot_id"),
    )
    context = ForecastContext(
        products={product.sku: product},
        sales_history=history,
        overrides=overrides,
    )
    result = _get_forecaster().forecast(request, context)
    return _serialize_result(result)


def handler(job: dict) -> dict[str, Any]:
    payload = job.get("input") if isinstance(job, dict) else None
    if not isinstance(payload, Mapping):
        return {"ok": False, "error": "job.input must be an object"}

    action = str(payload.get("action") or "").strip().lower()
    prompt = str(payload.get("prompt") or "").strip().lower()
    if action in {"health", "ping"} or prompt in {"health", "ping"}:
        checkpoint = _checkpoint_path()
        return {
            "ok": True,
            "status": "healthy",
            "model_path": str(checkpoint),
            "model_available": checkpoint.exists(),
            "device": _device(),
        }

    try:
        result = _forecast(payload)
    except Exception as exc:
        LOGGER.exception("Forecast request failed")
        return {
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
    return {"ok": True, "result": result}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
