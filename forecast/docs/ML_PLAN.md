# ML demand forecast plan

## Goal

Add an optional ML demand forecast behind the existing `Forecaster` protocol. The ML path predicts daily demand quantiles; the rule-based `BaselineForecaster` stays the safety net and the comparison baseline.

The ML model never produces the final action. `ReorderService` still applies safety stock, shelf-life caps, MOQ rounding, and the bakery/generic policies. The ML forecast only replaces the demand estimate.

## Architecture

```text
Synthetic / real sales history
        ↓
forecast.ml.features      # lags, rolling stats, calendar, product metadata
        ↓
forecast.ml.model         # PyTorch MLP with SKU + category embeddings
        ↓
quantiles q10 / q50 / q90
        ↓
forecast.ml.forecaster    # MLForecaster implements Forecaster
        ↓
forecast.reorder          # BUY / BAKE / HOLD / MARKDOWN
```

Modules:

| Module | Responsibility |
|---|---|
| `forecast/ml/config.py` | YAML + `MLFLOW_*` / `FORECAST_ML_*` environment settings |
| `forecast/ml/catalog.py` | Deterministic expanded synthetic catalog for training |
| `forecast/ml/features.py` | Lag/rolling/calendar features and the fitted encoder |
| `forecast/ml/dataset.py` | Supervised examples and time-based split |
| `forecast/ml/model.py` | `DemandNet`, pinball loss, checkpoint save/load |
| `forecast/ml/train.py` | Training loop, evaluation, MLflow logging, registry update |
| `forecast/ml/evaluate.py` | Pinball, coverage, MAE/WAPE/bias, promotion gate |
| `forecast/ml/registry.py` | Offline alias registry (`challenger`, `champion`) |
| `forecast/ml/forecaster.py` | `MLForecaster` with baseline fallback |
| `forecast/ml/mlflow_client.py` | Optional MLflow tracker (no-op when disabled) |

## Data rules

- Aggregate all dayparts to one daily total per product.
- Exclude `is_stockout_censored=True` days as targets. Lag gaps caused by stockouts or missing days are forward-filled with the last observed value, never treated as zero demand.
- Use only observations at or before the forecast anchor date.
- Target is the next day's demand. At inference the anchor stays fixed and each horizon day is predicted directly, so no recursive drift.
- Calendar features include the target day's weekday, month, and holiday/promotion multiplier. This lets a new override affect the forecast without retraining.

## Features

Numeric features are standardized with training-set mean/std:

- Lags: 1, 2, 3, 7, 14, 28 days.
- Rolling mean over 7 and 28 days, 28-day standard deviation and coefficient of variation.
- Days since the last sale and forecast horizon.
- Target-day weekday, weekday sin/cos, weekend flag, month sin/cos, holiday multiplier.
- Product metadata: shelf life, lead time, MOQ, safety-stock days, bakery flag.
- Categorical embeddings: product SKU and category. Index `0` is reserved for unknown.

## Model

- One global model across products. This is deliberate: a shared model learns weekday and calendar behaviour from every SKU and works for new products through category embeddings.
- SKU and category embeddings concatenated with numeric features.
- MLP hidden sizes `64 → 32` with dropout, three quantile outputs.
- Pinball loss over `q10`, `q50`, `q90`.
- Predictions are clamped to non-negative and sorted per day.
- CPU-only training is expected. `pyproject.toml` pins torch to the PyTorch CPU index, and the default run takes about 30–60 seconds on a laptop CPU.

## Evaluation and promotion gate

Validation is a time-based holdout (last 20% of target dates), not a random split.

Reported metrics:

- Pinball loss (quantile quality).
- 80% interval coverage: share of actuals inside `[q10, q90]`.
- MAE, WAPE, and bias of the median forecast.
- Baseline WAPE/bias for the same examples.

The gate in `forecast/ml/evaluate.py` promotes only when all hold:

- ML WAPE is not more than 1 percentage point worse than the baseline.
- Absolute bias is at most 10% of mean actual demand.
- 80% coverage is within 72–88%.

The 1-point WAPE tolerance is intentional: on the synthetic data the baseline is near the noise floor, so requiring a strict win would block every run. Tighten the tolerance once real data exists.

## Fallback behaviour

`MLForecaster` falls back to `BaselineForecaster` and adds `ML_FALLBACK_BASELINE` when:

- the checkpoint is missing or cannot be loaded;
- the SKU was not in the training vocabulary;
- there is no usable history;
- the last sale is older than the stale threshold;
- fewer than 14 valid days exist in the 28-day window.

The baseline result keeps its original reason codes, so the UI can explain the fallback. ML results add `ML_FORECAST`, and `ML_LOW_COVERAGE` when fewer than 21 valid days are available.

## MLflow and registry

Local defaults:

- Tracking store: `sqlite:///forecast/artifacts/mlflow.db`.
- Experiment: `inventory-demand`.
- Run artifacts: `model.pt` and `evaluation.json`.
- Offline registry: `forecast/artifacts/registry.json`, with copied checkpoints under `forecast/artifacts/registry/`.
- Alias flow: every run registers `challenger`; a passing run also becomes `champion`.

Remote MLflow uses environment variables only:

```bash
export MLFLOW_TRACKING_URI=https://mlflow.example.com
export MLFLOW_TRACKING_USERNAME=...
export MLFLOW_TRACKING_PASSWORD=...
export MLFLOW_REGISTRY_URI=https://mlflow.example.com
export MLFLOW_EXPERIMENT_NAME=inventory-demand
export MLFLOW_MODEL_NAME=demand_forecaster
export MLFLOW_MODEL_ALIAS=champion
```

Do not hard-code credentials. The tracker currently logs runs and artifacts remotely. Model-version aliases are maintained in the local registry until the remote model artifact format and registry permissions are confirmed.

## Commands

```bash
uv sync --group ml
uv run python -m forecast.ml.train
uv run python -m forecast.ml.train --days 365 --products 24 --epochs 20
uv run python -m forecast.ml.train --no-mlflow --no-register
uv run python -m forecast.cli --forecaster ml --backtest
uv run pytest forecast/tests -q
uv run mlflow ui --backend-store-uri sqlite:///forecast/artifacts/mlflow.db
```

## Current status

- Model, features, training, evaluation, fallback, MLflow tracking, and local alias registry are implemented.
- Test coverage: ML features, dataset split, checkpoint round-trip, forecaster fallback, registry aliases, promotion gate.
- Sample default run on synthetic data: WAPE 13.3% (baseline 13.1%), bias -0.68 units, 80% coverage 83.6%, 8,363 validation examples.
- Not done: remote model-version aliases, auction/quantile calibration on real data, per-daypart targets, GPU training, and API/dashboard integration.

## Known limitations

- Training data is synthetic; metrics show the pipeline works, not real-world accuracy.
- The generator encodes weekday, holiday, and annual effects. The baseline already captures most of that signal, which is why the ML gain is small.
- The model uses one anchor date for all horizon days. It avoids recursive drift but does not explicitly model multi-day demand paths.
- Quantile intervals are calibrated on the validation split only.
- The local registry is a demo-grade alias store, not a replacement for MLflow's registry.
