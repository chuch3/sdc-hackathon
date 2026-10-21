# AGENTS.md

## Repo status

- Still an early scaffold: there is no `app/`, `scripts/`, CI, or lint config yet. The implemented feature lives in `forecast/` with tests in `forecast/tests/`.
- Current product is the perishable food inventory system described in `README.md` and `docs/`. Ignore `pyproject.toml`'s stale description ("Orbyte Chase: human-approved overdue invoice follow-up for SMEs").
- Python is pinned to 3.11.12 (`.python-version`, `requires-python >=3.11.12`) and managed with `uv`; use the existing `.venv`, not `pip`/`python -m venv`.

## Commands

- `uv sync` — install/refresh the core + dev dependencies.
- `uv sync --group ml` — install the ML extras (`torch`, `mlflow`, `pyyaml`).
- `uv run pytest` — run `forecast/tests` (`testpaths` is set to `forecast/tests`).
- `uv run pytest -q forecast/tests/test_file.py::test_name` — run one test.
- `uv run python -m forecast.cli --backtest` — baseline recommendation demo.
- `uv run python -m forecast.cli --forecaster ml` — ML recommendation demo; falls back to baseline when no checkpoint exists.
- `uv run python -m forecast.ml.train` — train, evaluate, log to MLflow, and update the local alias registry.
- `uv run mlflow ui --backend-store-uri sqlite:///forecast/artifacts/mlflow.db` — inspect runs locally.
- No lint, typecheck, or CI is configured. README plans Ruff but it is not a dependency/config; add it before claiming lint passes.

## Stack mismatch (important)

- Installed core deps: FastAPI, Flask, matplotlib, pandas, requests. Dev group: pytest. ML group: torch (CPU wheel from the PyTorch CPU index), mlflow, pyyaml.
- README plans SQLAlchemy + SQLite + Streamlit integration; no `app/` or dashboard exists yet, so do not assume those imports work.
- ML artifacts are local (`forecast/artifacts/`) and gitignored. Remote MLflow is configured only through `MLFLOW_*` env vars; never hard-code credentials.

## Docs

- `README.md` is the canonical build plan but duplicates `docs/perishable-inventory-plan.md` plus `docs/readme-additions.md`. Update the docs and README together to avoid drift.
- ML design and caveats live in `forecast/docs/ML_PLAN.md` and `forecast/docs/MODEL_CARD.md`.
- When scaffolding the app, follow the planned layout: `app/{api,core,db,models,schemas,services,domains,analytics}`, `dashboard/`, `scripts/`, `tests/`, `docs/`.

## Domain guardrails

- All quantity changes are immutable `stock_movements` rows; FEFO allocates earliest-expiry first and excludes expired/quarantined/donated stock. Never allow selling expired product.
- Reorder math uses saleable on-hand, not raw on-hand.
- Keep bakery behavior behind the `DemandPolicy` / `PlanningPolicy` / `AdvicePolicy` interfaces; no `if bakery` branches in services.
- Treat SDG, CO2e, and meal-equivalent outputs as estimates and surface assumptions.
- `data/*.db`, `data/outbox/`, and `data/smoke/` are gitignored; never commit generated databases or outbox files.
- Never train on stockout-censored days as if they were true low demand, and never let an ML forecast bypass the `Forecaster` fallback to the rule-based baseline.
- Promotion requires the gate in `forecast/ml/evaluate.py`: no material WAPE regression, bias within tolerance, and calibrated 80% coverage.
