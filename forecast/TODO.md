# Forecast / Reorder TODO

This is the working checklist for the whole forecast feature. `[x]` means the scaffold implements it; `[ ]` is still required before the feature is demo-complete.

## 1. Contracts and inputs

- [x] Product catalog fields: shelf life, lead time, review period, MOQ, case size, service level, weekday factors, daypart shares, near-expiry threshold.
- [x] `SalesObservation` demand history with daypart and stockout-censoring flag.
- [x] `CalendarOverride` for holidays and promotions.
- [x] `InventoryPosition` with saleable on-hand, on-order, remaining shelf life, and optional forecast error.
- [x] `ForecastRequest`, `ForecastResult`, `Recommendation`, and reason-code enums.
- [x] `ForecastRepository` protocol plus in-memory adapter.
- [x] JSON input loader for products, sales history, inventory, and overrides.
- [x] SQLAlchemy/FastAPI repository adapter against M1/M2 tables.
- [ ] Persist forecast runs, input snapshots, recommendations, and approval state.
- [x] Confirm with M2 how stockout/censored days are stored or derived (`stockout_events`).
- [x] Confirm with M4 ownership of `DemandPolicy` and bakery factors.

## 2. Synthetic demand generator

- [x] Deterministic seed and reproducible output.
- [x] Generic and bakery product profiles.
- [x] Weekday, seasonal, holiday, and promotion effects.
- [x] Bakery daypart split: morning, midday, afternoon, evening.
- [x] Simulated stockouts with separate ground-truth demand.
- [x] Cold-start, sparse, and zero-demand edge cases in unit tests.
- [x] Inventory snapshots that exercise BUY, BAKE, HOLD, and MARKDOWN.
- [ ] Configurable catalog instead of the hard-coded sample shop.
- [ ] CSV/JSON export and seed-loader integration.
- [ ] Larger scenario library for demo day and backtests.

## 3. Forecast model

- [x] Trailing 28-day mean.
- [x] Exclude stockout-censored days.
- [x] Category-average fallback for new products.
- [x] Weekday, holiday/promotion, and daypart adjustments through policies.
- [x] 80% uncertainty interval and confidence label.
- [x] Data-quality flags: valid days, censored days, cold start, stale.
- [x] Plain-language `why` lines.
- [x] Non-actionable result when history is missing or stale.
- [ ] Rolling-origin backtest service.
- [ ] Per-daypart forecast rather than a daily total multiplied by share.
- [ ] Tune fallback thresholds and confidence bands against backtests.
- [ ] Add an explicit missing-days policy and data-freshness check from M1.

## 4. Metrics

- [x] MAE in units.
- [x] MAPE over non-zero actuals with excluded-day count.
- [x] Bias with documented sign convention.
- [x] WAPE as the robust primary metric.
- [x] Single-cutoff backtest.
- [ ] Rolling-origin backtest report.
- [ ] Per-product and aggregate CSV export.
- [ ] Plain-language metric glossary for the approval screen.
- [ ] Backtest stockout days separately from normal days.

## 5. Recommendation engine

- [x] `BUY` for generic replenishment.
- [x] `BAKE` for bakery replenishment.
- [x] `HOLD` when stock covers demand.
- [x] `MARKDOWN` for near-expiry surplus.
- [x] Safety stock, reorder point, saleable on-hand, on-order, shelf-life cap, and MOQ rounding.
- [x] Expiry-risk label.
- [x] Three-line rationale and `why` explanations.
- [x] `approval_required=True` on every recommendation.
- [x] Read-only service; no stock movement is created.
- [x] Fresh cap includes safety stock, correcting the README formula where `min(raw_order, fresh_cap)` would otherwise make safety stock ineffective.
- [x] `REDUCE`, `DONATE`, and `WRITE_OFF` actions are represented in contracts; `WRITE_OFF` is recorded through M2 stock actions.
- [ ] Markdown windows and discount percentage.
- [x] Purchase-order/on-order integration.
- [ ] Full approval state machine (approved/edited/rejected are recorded; expiry/done transitions remain).
- [x] Preserve the recommendation action/quantity and override reason in activity events.
- [x] Sales/issue endpoint that calls M2 FEFO and hard-blocks expired stock.

## 6. Tests and verification

- [x] 43 unit tests for metrics, generator, forecaster, reorder, JSON input, pipeline, and the ML path.
- [x] Determinism, censored demand, cold start, holiday override, daypart, and missing history.
- [x] All four recommendation actions produced by the sample data.
- [x] Pipeline does not mutate inventory.
- [x] Integration tests against the real M2 movement ledger.
- [x] API contract tests with M1.
- [x] Expired-stock and zero-demand edge-case tests in the full app.
- [ ] Performance check: forecast 20+ products in under 2 seconds.

Run:

```bash
uv run pytest forecast/tests -q
uv run python -m forecast.cli --backtest
```

## 7. Docs and handoff

- [x] `forecast/README.md` with inputs, outputs, commands, and limitations.
- [x] `forecast/TODO.md`.
- [ ] Add the M3 Day 1 checklist to root `README.md` and mirror it in `docs/perishable-inventory-plan.md`.
- [x] Add the forecast commands to `AGENTS.md`.
- [ ] Add example import files or a seed command for the demo.
- [ ] Document model assumptions, synthetic-data caveat, and metric caveats in the root docs.
- [ ] Add the approval-screen glossary and reason-code mapping for M5.

## 8. ML demand model (stretch)

- [x] Optional `ml` dependency group: torch, mlflow, pyyaml.
- [x] Deterministic expanded synthetic catalog for training.
- [x] Lag, rolling, calendar, and product features; encoder serialized in the checkpoint.
- [x] Global PyTorch MLP with SKU/category embeddings and q10/q50/q90 heads.
- [x] Pinball loss, time-based validation split, early stopping.
- [x] Checkpoint save/load and local alias registry (`challenger`, `champion`).
- [x] MLflow tracking with SQLite default and remote `MLFLOW_*` env vars.
- [x] WAPE/bias/coverage promotion gate.
- [x] `MLForecaster` with baseline fallback for missing, unseen, stale, and low-coverage cases.
- [x] CLI `--forecaster ml`.
- [x] ML tests for features, dataset split, checkpoint, fallback, registry, and gate.
- [ ] Wire remote MLflow model-version aliases after registry permissions are confirmed.
- [ ] Calibrate intervals on real data; synthetic coverage is not evidence.
- [ ] Per-daypart ML targets rather than a daily total multiplied by share.
- [ ] Rolling-origin ML backtest and champion/challenger shadow mode.
- [ ] API/dashboard integration and a fallback badge in the approval screen.

## 9. Day 1 gate

- [x] App starts and seed data loads through M1.
- [x] Forecast, metrics, and recommendation contracts are implemented and tested.
- [x] Synthetic sample shop loads in memory.
- [x] CLI demonstrates BUY, BAKE, HOLD, MARKDOWN, and a backtest.
- [x] Contracts reviewed with M1, M2, M4, and M5 and frozen.
