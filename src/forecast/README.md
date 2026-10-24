# Forecast / Reorder scaffold

This folder is a standalone scaffold for the M3 Forecast/Reorder work. It reads sales history and inventory inputs, forecasts demand, and outputs a human-approvable stock recommendation: `BUY`, `BAKE`, `HOLD`, or `MARKDOWN`.

It does not write to the database and never changes stock. It is the “Logic” layer between M2’s immutable movement ledger and the approval screen.

## Flow

```text
M2 sales movements + M1 product/inventory data + calendar overrides
        ↓
forecast.contracts ForecastContext
        ↓
BaselineForecaster
        ↓
ForecastResult (demand + range + confidence + why)
        ↓
ReorderService
        ↓
Recommendation (BUY / BAKE / HOLD / MARKDOWN)
        ↓
M5 approval screen
```

## Run

```bash
uv run python -m forecast.cli
uv run python -m forecast.cli --backtest
uv run python -m forecast.cli --json
uv run python -m forecast.cli --input path/to/input.json
uv run python -m forecast.cli --forecaster ml
uv run pytest forecast/tests -q
```

The default command generates deterministic synthetic data, forecasts all products, prints recommendations, and optionally runs a holdout backtest.

## Inputs

The repository protocol is in `repository.py`:

```python
products() -> Sequence[Product]
sales_history() -> Sequence[SalesObservation]
inventory() -> Sequence[InventoryPosition]
overrides() -> Sequence[CalendarOverride]
```

`SalesObservation` is demand history, not the raw movement log. Pass only sales/issues; receipts, waste, adjustments, and donations must not be treated as demand. Use `is_stockout_censored=True` when a zero/low-sale day was caused by empty shelves.

JSON input accepted by `--input`:

```json
{
  "products": [
    {
      "sku": "sourdough",
      "name": "Sourdough loaf",
      "category": "bakery",
      "domain": "bakery",
      "shelf_life_days": 2,
      "lead_time_days": 1,
      "review_period_days": 1,
      "moq": 5,
      "case_size": 5,
      "service_level": 0.95,
      "weekday_factors": {"5": 1.3},
      "daypart_shares": {"morning": 0.45, "midday": 0.3, "afternoon": 0.18, "evening": 0.07}
    }
  ],
  "sales_history": [
    {
      "product_sku": "sourdough",
      "business_date": "2026-10-01",
      "quantity": 40,
      "daypart": "morning",
      "is_stockout_censored": false
    }
  ],
  "inventory": [
    {
      "product_sku": "sourdough",
      "saleable_on_hand": 25,
      "on_order": 0,
      "remaining_shelf_life_days": 2
    }
  ],
  "overrides": [
    {
      "business_date": "2026-10-21",
      "multiplier": 1.4,
      "product_sku": "sourdough",
      "kind": "holiday"
    }
  ]
}
```

## Output

Every recommendation includes:

- `action`: `BUY`, `BAKE`, `HOLD`, or `MARKDOWN`
- `quantity`
- `rationale` and `why`: plain-language evidence
- `confidence`: low, medium, or high
- `expiry_risk`: expired, critical, warning, or healthy
- `calculation`: on-hand, on-order, forecast total, safety stock, reorder point, raw order, fresh cap, surplus
- `forecast`: the full demand forecast behind the recommendation
- `forecast_run_id` and `input_snapshot_id`
- `approval_required`: always `True`

The scaffold never auto-approves and never records a stock movement.

## Forecast behaviour

- Uses a trailing 28-day mean of observed sales.
- Excludes days marked `is_stockout_censored` rather than treating them as true low demand.
- Falls back to the product-category average when the product has fewer than 14 valid days.
- Applies weekday, holiday/promotion, and bakery daypart factors through `DemandPolicy`.
- Reports an 80% interval from historical variability.
- Marks forecasts as non-actionable when history is missing or stale.
- Defaults to the rule-based baseline. `--forecaster ml` swaps in the quantile model.

## ML extension

`forecast/ml/` is an optional demand model behind the same `Forecaster` protocol.

```bash
uv sync --group ml
uv run python -m forecast.ml.train       # train, evaluate, log, register
uv run python -m forecast.cli --forecaster ml --backtest
```

The model predicts daily `q10`, `q50`, and `q90` demand. `q50` becomes the point forecast; `q10`–`q90` becomes the 80% interval. `ReorderService` still applies safety stock, shelf-life caps, MOQ rounding, and the domain policies. See `docs/ML_PLAN.md` and `docs/MODEL_CARD.md`.

Fallback: the ML forecaster uses `BaselineForecaster` when the checkpoint is missing, the SKU is unseen, or history is missing/stale/low-coverage. The result keeps both reason-code sets so the UI can explain what happened.

MLflow:

```bash
export MLFLOW_TRACKING_URI=https://mlflow.example.com   # optional
export MLFLOW_TRACKING_USERNAME=...
export MLFLOW_TRACKING_PASSWORD=...
uv run mlflow ui --backend-store-uri sqlite:///forecast/artifacts/mlflow.db
```

Local artifacts (`forecast/artifacts/`, `*.pt`, `mlflow.db`) are gitignored. The offline alias registry lives at `forecast/artifacts/registry.json`.

## Recommendation behaviour

- Safety stock: `z × forecast_error × sqrt(lead_time + review_period)`.
- Reorder point: `forecast(lead_time + review_period) + safety_stock`.
- Raw order: `reorder_point - saleable_on_hand - on_order`.
- Fresh cap: `forecast(min(remaining_shelf_life, lead_time + review_period)) + safety_stock - saleable_on_hand`.
- Recommended: `max(0, min(raw_order, fresh_cap))`, rounded up to MOQ/case size.
- Near-expiry surplus is recommended for `MARKDOWN` before replenishment.
- `BUY` is used for generic products; `BAKE` is used for bakery products through `PlanningPolicy`.

Note: the README formula omits safety stock from `fresh_cap`. That makes safety stock ineffective whenever the cap binds. This scaffold includes safety stock in the fresh cap so the reorder point still protects service level; the decision is documented in `TODO.md`.

## Policy boundary

`DemandPolicy`, `PlanningPolicy`, and `AdvicePolicy` live in `policies.py`. Bakery behaviour is selected there, not with `if bakery` branches in the forecasting or reorder services. M4 should own/replace the bakery policy implementation.

## Layout

```text
forecast/
  contracts.py       dataclasses and enums
  policies.py        demand, planning, and advice policies
  synthetic.py       deterministic sample data
  repository.py      input protocol and in-memory adapter
  io.py              JSON input loader
  baseline.py        28-day baseline forecaster
  metrics.py         MAE, MAPE, bias, WAPE, backtest
  reorder.py         recommendation engine
  pipeline.py        forecast + reorder orchestration
  cli.py             runnable demo
  ml/                optional ML forecaster, training, registry
  docs/              ML plan and model card
  TODO.md            full implementation checklist
  tests/             unit and ML tests
```

## Current limitations

- No database/API adapter yet; use `InMemoryRepository` or JSON.
- No persistence of forecasts, recommendations, approvals, or outcomes.
- No rolling-origin backtest report; the scaffold has a single-cutoff backtest.
- No `REDUCE`, `DONATE`, or `WRITE_OFF` actions yet.
- Expired-sale blocking, FEFO, and expiry buckets belong to M2 and are not reimplemented here.
- Synthetic data is for demos and tests only.
- ML is a demo-grade challenger; the default run is within 1 WAPE point of the baseline, not a proven improvement.
- Remote MLflow model-version aliases are not wired yet; local aliases are.
