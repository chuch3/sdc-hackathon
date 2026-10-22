# Perishable Food Inventory System — 5-Day Build Plan

## Assumptions

- Greenfield project, ~25 person-days total (5 people × 5 days × ~6 focused hours).
- Prototype/MVP for demonstration, not production deployment.
- Single location, no authentication, synthetic seed data.
- Python 3.11+, FastAPI, SQLite, Streamlit, pytest, Ruff; optional PyTorch + MLflow for the ML challenger.
- Bakery mode is a **domain plugin**, not a separate fork.

## 1. MVP Scope

The system answers three questions:

1. **What is about to expire, and what should we do with it?**
2. **What do we need to buy or bake, and how much?**
3. **What waste, stockout, and sustainability impact are we creating?**

### Must have

- Product, supplier, and batch/lot tracking.
- Receipts, sales/issues, waste, adjustments, donations.
- FEFO stock deduction: First-Expired-First-Out.
- Expiry buckets and alerts: expired, critical, warning, healthy.
- Demand forecast using recent history and weekday patterns.
- Buy / hold / reduce recommendation with a written rationale.
- Dashboard with inventory, expiry, recommendations, and KPIs.
- Bakery mode: daily bake plan, daypart demand, seasonal ingredient advice.
- SDG impact dashboard.
- Seed data, tests, README, and demo script.

### Defer / out of scope

Authentication, multi-warehouse, POS/ERP integration, automated supplier emails, full recipe/MRP planning, mobile app, payment processing. The optional ML forecast is a declared stretch behind the rule-based default; see `forecast/docs/ML_PLAN.md`.

## 2. Architecture

```text
Streamlit dashboard
        │ HTTP/JSON
FastAPI REST API
        │
Service layer
  ├── inventory + FEFO
  ├── expiry risk + alerts
  ├── forecasting
  ├── reorder / production planning
  ├── waste + donations
  └── SDG metrics
        │
Domain policies (Strategy pattern)
  ├── generic perishables
  └── bakery
        │
SQLAlchemy → SQLite (Postgres-ready)
```

### Why this design

- **One inventory ledger** for all domains. Bread production is just a receipt into inventory; sales and waste are issues.
- **Domain strategy** avoids `if bakery` scattered through the codebase. Bakery supplies different forecasting, planning, and advice rules.
- **FastAPI + Streamlit** allows backend and UI work in parallel.
- **SQLite** is enough for the demo; use SQLAlchemy so Postgres is a later configuration change.
- **Rule-based, explainable recommendations are the default.** A rules-first baseline is easier to defend in a report; the ML challenger is optional and must fall back to the baseline.

Suggested structure:

```text
app/
  api/            # FastAPI routes
  core/           # config, settings
  db/             # session, migrations
  models/         # SQLAlchemy tables
  schemas/        # Pydantic request/response models
  services/       # inventory, expiry, forecasting, reorder, waste
  domains/        # base policy + generic + bakery
  analytics/      # SDG metrics
dashboard/        # Streamlit pages
scripts/          # seed, expiry scan, forecast refresh
tests/
docs/
```

## 3. Core Data Model

| Table | Purpose / key fields |
|---|---|
| `products` | SKU, name, category, unit, shelf life days, storage type, supplier, lead time, MOQ, safety-stock days, allergens, seasonal flag, domain |
| `suppliers` | Name, lead time, minimum order quantity, reliability |
| `batches` | Product, quantity received/remaining, received date, baked date, expiry date, unit cost, status |
| `stock_movements` | Immutable ledger: receipt, sale, waste, adjustment, donation, transfer; timestamp, daypart, reason |
| `purchase_orders` | Supplier, status, expected date, lines |
| `bread_profiles` | Product, weekday factor, daypart share, production constraints |
| `seasonal_ingredients` | Ingredient, months available, availability score, price index, local flag |
| `production_plans` | Date, product, daypart, planned quantity, actual baked, sold, discarded |
| `holiday_calendar` | Date, expected demand multiplier |
| `settings` | Expiry thresholds by category, service level, waste/CO2e factors |
| `sdg_factors` | Category-level kg CO2e per kg waste, meals per kg donated |

Optional stretch: `recipes` and `recipe_items` for ingredient-level production planning.

Important: every quantity change is a movement. This gives an audit trail for food safety and SDG reporting.

## 4. Core Decision Logic

### FEFO

When stock is issued:

1. Select available batches for the product.
2. Sort by earliest expiry, then earliest received/baked time.
3. Allocate quantities until the request is satisfied.
4. Record one movement per batch.
5. Exclude expired, quarantined, or donated stock.

### Expiry risk

```text
days_to_expiry = expiry_date - today
```

Buckets:

- Expired: `< 0`
- Critical: `0` to category threshold
- Warning: threshold to `2 × threshold`
- Healthy: beyond warning

Thresholds are configurable: bakery 1 day, dairy 3 days, produce 2 days, meat 1–2 days.

Risk score weights quantity by proximity to expiry and inventory value. The system suggests:

- **Markdown** if expected sales before expiry are lower than remaining quantity.
- **Donate** if safe and a partner is configured.
- **Write off** only when expired/unsafe.
- **Stop replenishment** if surplus is already at risk.

Never allow sale of expired product. Advice is decision support, not food-safety certification.

### Forecasting

Start simple and explainable:

```text
forecast = baseline_demand
         × weekday_factor
         × seasonal/holiday_factor
         × daypart_share        # bakery only
```

- Use trailing 28 days, with fallbacks for new products.
- Holidays and promotions are manual overrides.
- Measure MAE/MAPE and bias on a holdout period.
- Show forecast confidence; do not hide uncertainty.
- Flag stockout days as censored demand rather than treating them as true low demand.

Optional ML challenger:

- Predicts daily q10/q50/q90 demand with one global model and product/category embeddings.
- Stays behind the same `Forecaster` interface and falls back to the baseline on missing, stale, unseen, or low-coverage products.
- Is promoted only if WAPE does not regress, bias stays within 10%, and 80% coverage lands near 80%.
- Never creates a stock movement and never bypasses human approval.
- Training, MLflow, and the model card live in `forecast/ml/` and `forecast/docs/`.

### Reorder recommendation

Use **saleable on-hand**, not raw on-hand: stock expiring before the new order arrives cannot prevent a stockout.

```text
ROP = forecast(lead_time + review_period) + safety_stock
safety_stock = z × forecast_error × sqrt(lead_time + review_period)

raw_order = ROP - saleable_on_hand - on_order
fresh_cap = forecast(min(remaining_shelf_life, lead_time + review_period))
            - saleable_on_hand
recommended = max(0, min(raw_order, fresh_cap))
```

Round up to MOQ/case size. If the product already has near-expiry surplus, suppress the order and recommend markdown/donation instead.

Each recommendation returns:

```text
action: BUY | HOLD | REDUCE | MARKDOWN | DONATE | BAKE
quantity, rationale, confidence, expiry risk, forecast horizon
```

## 5. Bakery / Bread Domain Extension

Bakery mode uses the same inventory core but changes the planning policy.

### Additional behavior

- **How many bread per day:** forecast by weekday, add a small buffer, subtract safe carryover, then split by daypart.
- **Time of day:** morning, midday, afternoon, evening demand shares.
- **Day of week:** weekend and Monday effects learned from sales history.
- **Seasonal ingredients:** calendar of in-season fruits, nuts, spices, and local availability/price.
- **Seasonal bread advice:** rule-based suggestions such as autumn pumpkin-seed rye or winter stollen.
- **Markdown windows:** discount remaining bread at configured times, then donate before close if policy permits.
- **Ingredient constraints:** check flour, yeast, butter, and seasonal ingredient stock against the bake plan.
- **Allergens:** gluten, dairy, nuts, eggs must be stored and displayed.

Example output:

```text
Saturday sourdough
Bake: 118 loaves
Morning: 65 | Midday: 35 | Afternoon: 18
Reason: weekend factor 1.18 × base 100, 6% buffer, no safe carryover
Advice: apple-walnut loaf is in season; markdown 30% after 17:30
```

### Transition mechanics

Define interfaces such as:

- `DemandPolicy`: weekday/daypart/seasonal adjustments.
- `PlanningPolicy`: purchase versus production logic.
- `AdvicePolicy`: markdown, donation, seasonal recommendations.

`GenericPerishablePolicy` and `BakeryPolicy` implement these. The core services and expiry ledger remain unchanged. Enable with configuration such as `DOMAIN=bakery` or a UI toggle.

## 6. UN SDG Alignment

| SDG target | System contribution | KPI |
|---|---|---|
| **SDG 2.1** — safe, nutritious food access | Reduce stockouts; route safe surplus to donation partners | Availability %, donation kg, meals equivalent |
| **SDG 2.4** — sustainable food production | Seasonal/local ingredient advice; demand-aligned baking | Seasonal/local ingredient %, overproduction % |
| **SDG 12.3** — halve food waste | FEFO, expiry alerts, demand-based buying/baking, markdowns | Waste rate %, expired stock value, surplus units |
| **SDG 12.5** — waste prevention | Markdown/donation before waste; waste analytics | Kg diverted from waste, markdown sell-through |
| **SDG 13.2** — climate integration | Avoided waste and overproduction reduce emissions | Estimated kg CO2e avoided |

Impact logic:

```text
less over-ordering → less surplus → fewer markdowns and write-offs
FEFO + alerts → more stock sold before expiry
safe surplus → donation instead of waste
seasonal/local sourcing → lower footprint and better availability
```

Report these as **estimated contributions**, not certified SDG impact. Show the baseline policy, assumptions, and emission factors.

## 7. Five-Day Timeline

| Day | Focus | End-of-day gate |
|---|---|---|
| **Day 1** | Foundations: scope, SDG KPIs, ERD, API contract, domain interfaces, repo, schema, synthetic data, Streamlit shell | App starts, seed data loads, schema/API/domain contracts frozen |
| **Day 2** | Inventory truth: products, batches, receipts, sales, waste, FEFO, expiry buckets/alerts, baseline forecast, inventory view | Demo: add batch → sell → FEFO deducts → expiry alert appears |
| **Day 3** | Decisions: safety stock, reorder quantities, saleable on-hand, near-expiry actions, bakery profiles, bake plan, seasonal advice, KPI dashboard | Scenario review passes; every recommendation has a reason code |
| **Day 4** | Integration and hardening: E2E tests, edge cases, backtests, indexes, CSV export, Docker optional, docs | Clean-slate demo works; test suite green; no P0 bugs |
| **Day 5** | Polish and storytelling: final fixes, README, SDG report, slides, screenshots, rehearsal | Feature freeze at noon; 5-minute demo delivered; tagged release |

Daily rhythm: 15-minute standup, merge by 16:30, checkpoint demo at 16:45. The gate must pass before starting the next day's work.

## 8. Task Distribution — 5 Members × 5 Days

| Member | Day 1 | Day 2 | Day 3 | Day 4 | Day 5 |
|---|---|---|---|---|---|
| **M1 — Backend/Data** | Repo, config, SQLAlchemy schema, migrations, seed loader | Product/supplier/batch CRUD, validation, API endpoints | Purchase orders/on-order, recommendation endpoint | Indexes, CSV export, Docker, integration fixes | ERD/architecture docs, deploy notes, final fixes |
| **M2 — Inventory/Expiry** | FEFO contract and algorithm, movement model, unit tests | Receipt/issue/waste/adjustment services, expiry buckets and alerts | Markdown/donation/waste actions, risk score, scheduled expiry scan | Partial batches, returns, timezone, concurrency, regression tests | Validate expiry math, final fixes, demo support |
| **M3 — Forecast/Reorder** | Synthetic demand generator, forecast interface, baseline model, metric definitions | Weekday-seasonal forecast, backtest MAE/MAPE, demand aggregation | Safety stock, saleable on-hand, order quantity with shelf-life cap, SDG KPI service | End-to-end backtest, cold-start defaults, tuning | SDG impact report numbers, forecast caveats, demo support |
| **M4 — Bakery Domain** | Domain interfaces, bakery tables/schema, seasonal calendar seed | Bread weekday/daypart profiles, bake-plan skeleton | Daily bake plan, seasonal advice, markdown windows, ingredient checks | Bakery scenario tests, holidays, allergens, docs | Seasonal demo data, bakery narrative, final fixes |
| **M5 — UI/QA/Docs** | CI, README skeleton, Streamlit shell, wireframes, SDG mapping | Inventory and expiry views, API client | Recommendation view, bakery planner, KPI cards/charts | E2E tests, error/empty states, clean-seed reset, coverage report | README, SDG report, slides, screenshots, rehearsal, demo lead |

Everyone writes tests for their own code and reviews at least one PR. M5 is the QA lead, not the only tester. Pair M1/M5 on API–UI integration and M2/M3 on recommendation interfaces.

## 9. Risks and Guardrails

- **Five days is tight:** lock MVP scope on Day 1; no feature additions after Day 4.
- **Sparse demand data:** fallback defaults, manual overrides, confidence display, and a hard ML-to-baseline fallback; never let ML output bypass the baseline gate.
- **Stockout-censored demand:** flag affected days; do not train blindly on them.
- **Expiry/timezone bugs:** store UTC, compute local business dates, define whether expiry is start or end of day.
- **Concurrency:** wrap allocation in a database transaction; SQLite is acceptable for the demo.
- **Food safety:** hard block expired sales; markdown/donation only within safe policy; track allergens.
- **Domain coupling:** bakery logic stays behind policy interfaces.
- **SDG overclaiming:** display assumptions and label CO2e/meal figures as estimates.
- **Integration risk:** contract-first development, daily merges, one clean-seed demo by Day 4.

## 10. Deliverables and Demo

- Running FastAPI + Streamlit app with seed data.
- Batch-level inventory and FEFO transaction history.
- Expiry alerts and actionable recommendations.
- Bakery daily production plan with daypart and seasonal advice.
- SDG impact dashboard.
- `pytest` suite, README, architecture diagram, ERD, SDG report.
- Runnable `forecast/` scaffold with baseline + optional ML forecaster and offline alias registry.
- Five-minute demo:

1. Show expiry alerts and waste KPIs.
2. Record a sale and demonstrate FEFO.
3. Show a buy/hold/reduce recommendation with rationale.
4. Switch to bakery mode and show Saturday's bake plan by daypart and seasonal advice.
5. Show the estimated SDG impact.

## Recommended Defaults

Use **FastAPI + SQLite + Streamlit**, synthetic data, no authentication, and bakery as a domain toggle. Confirm those choices and this plan can be turned into the concrete repository skeleton, API contract, and day-by-day implementation checklist.

## Start here for the working demo

- `docs/USER_GUIDE.md` — client, manager, and stakeholder guide, including the SDG link.
- `docs/EXPLAINER.md` — technical plain-English walkthrough.
- `docs/UI_DESIGN.md` — Autumn Bakehouse tokens, layout, motion rules, and the editable CSS scaffold.
- `backend/README.md` and `forecast/README.md` — setup and engine details.
