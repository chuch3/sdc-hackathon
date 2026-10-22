# Perishable Food Inventory System — 5-Day Build Plan

> **FreshStock is a data-trust loop for small food shops.** It refuses to guess when
> history is missing, imports a messy sales CSV without inventing saleable stock, refreshes
> the shop's decisions from the live ledger, and separates forecast accuracy from causal
> impact claims. A person still approves every buying, baking, markdown, or donation action.

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
- Data-readiness stages with a safe refusal and next action instead of a fake forecast.
- CSV sales import with preview, skipped-row reporting, stockout markers, and idempotent
  commits that never alter today's saleable stock.
- A 30-second live loop with a data version and a changed-since card.
- Impact proof that reports holdout accuracy, observed outcomes, and a clearly labelled
  run-rate, plus a switchback A/B plan for causal attribution.

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
- Weekly quest board: a read-only seven-day projection with per-day action cards and an
  activity heatmap.
- `pytest` suite, README, architecture diagram, ERD, SDG report.
- Runnable `forecast/` scaffold with baseline + optional ML forecaster and offline alias registry.
- Five-minute demo:

1. Show expiry alerts and waste KPIs.
2. Record a sale and demonstrate FEFO.
3. Show a buy/hold/reduce recommendation with rationale, then approve it and show the
   recorded decision on the card.
4. Open the weekly quest board and read the workload bar and the projected week of cards; use **Show every task's reasoning** for the details.
5. Show the activity calendar under the board.
6. Switch to bakery mode and show Saturday's bake plan by daypart and seasonal advice.
7. Show the estimated SDG impact.

## Recommended Defaults

Use **FastAPI + SQLite + Streamlit**, synthetic data, no authentication, and bakery as a domain toggle. Confirm those choices and this plan can be turned into the concrete repository skeleton, API contract, and day-by-day implementation checklist.

# README Additions — Perishable Food Inventory System

## In one minute

This is a daily food-waste and stock helper for a small bakery or food shop. It watches expiry dates, estimates what will sell, and recommends what to sell first, discount, donate, buy, or bake.

A person approves every action that costs money or affects customers. Every decision is logged so the shop can learn from it and show what happened.

The current demo goes one step further than a forecast: it shows whether the data is ready, imports a messy CSV safely, refreshes from the live ledger, and separates measured forecast accuracy from an honest, labelled impact projection.

## The SME problem

An independent bakery or small food shop decides what to buy and bake from memory, habit, and a spreadsheet. It cannot see, batch by batch, what will expire first, how much will sell before then, or which products are already over-ordered.

Short-dated food is discovered too late, and there is no simple approval trail for discounts, donations, or extra purchases. The business loses twice: spoiled food becomes waste, and empty shelves become lost sales. The problem is sharpest for bread, dairy, and produce, where a one-day forecast error becomes either waste or a stockout.

**Who has the problem:** the owner or manager of an independent food shop or bakery with roughly 5–50 staff.

**Success looks like:** each morning, the owner gets one short, evidence-backed list — what to sell first, what to mark down or donate, what to buy or bake, and what to leave alone.

## Automated workflow with human control

The daily review follows one clear path:

```text
Trigger → Data → Logic → Approval → Logged outcome
```

| Stage | What it means | In this system | Human control |
|---|---|---|---|
| **Trigger** | What starts the review | Every day at 06:00, plus when a batch enters its critical expiry window | The manager can pause the schedule; every run gets an ID |
| **Data** | The facts the system reads | Batch quantities and expiry dates, sales by weekday and time of day, open orders, supplier lead times, seasonal ingredients, oven capacity | Sources and freshness are shown; missing or stale data blocks action |
| **Logic** | The rules that turn data into a recommendation | Oldest-first handling, expiry risk, demand estimate, saleable stock, buy/bake quantity, markdown or donation suggestion | Rules and thresholds are visible; a person can override with a reason |
| **Approval** | The person who decides | Manager or head baker reviews the evidence and approves, edits, or rejects | Required for purchases, markdowns, donations, and bake-plan changes |
| **Logged outcome** | The record of what happened | Run ID, input snapshot, recommendation, decision, approver, time, actual result | Append-only; approval reflects exactly what was shown; weekly review |

### Human control rules

- Automate the watching and the maths. People keep control of money, discounts, donations, and production changes.
- The default is no action. If nobody approves, or the approval times out, no purchase or discount happens.
- Every recommendation explains itself in three short lines: what expires, what demand is expected, and which rule fired.
- Approval limits are configurable: owner above a spend limit, manager for markdowns and donations, head baker for the bake plan.
- Expired food can never be sold. Allergen or ingredient checks can block a bake.
- Every override keeps the original recommendation and adds a reason.
- Start with every action approved. Later, only low-risk repeat actions may be auto-approved with sampling.
- One pause switch, role-based permissions, and a weekly review of waste, stockouts, and overrides.

```text
State flow:
Draft → Waiting for approval → Approved / Edited / Rejected / Expired
      → Done or Not done → Outcome logged
```

Bakery uses the same workflow. The recommendation is a daily bake plan, the head baker approves quantities by time of day, and actual baked, sold, and discarded amounts feed the next forecast.

## Orbyte fit and reuse

The system is a thin decision layer that fits the SME's existing routine. It does not replace the till, accounting, or supplier systems.

### Fit

- One named owner and one daily review screen.
- Uses the tools the shop already has: till export, supplier list, spreadsheets, email or chat.
- One clear approval path for spend, markdowns, donations, and baking.
- Small, rule-based, and explainable enough for a five-day build.
- Can be removed without breaking the shop's accounting or till.

### Reuse

- Product, supplier, sales, and purchase-order data instead of re-keying.
- Existing roles and approval channels.
- The same inventory ledger, approval queue, and audit log for normal food and bakery mode.
- Existing discount and donation policies.
- Open-source Python forecasting and reorder logic instead of custom infrastructure.

### Do not rebuild

Authentication, payments, accounting, ERP, barcode hardware, or a mobile app.

### Reuse checklist

- One owner, one workflow, one approval path.
- Existing data is imported, not entered twice.
- Existing staff roles are respected.
- Every action has an audit record.
- The business can measure waste, stockouts, and time saved.
- The system can be paused or removed safely.

If Orbyte is a specific platform, replace the generic fit-and-reuse language above with its actual triggers, connectors, approval queue, and logging.

## Business benefit and SDG link


| Business benefit | How it happens | How to measure | SDG link |
|---|---|---|---|
| Lower waste cost | Use oldest food first; mark down or donate early | Waste kg and value, expired stock value | SDG 12.3, 12.5 |
| Fewer empty shelves | Buy and bake closer to expected demand | Availability %, stockout days, lost sales | SDG 2.1 |
| Less cash tied up | Do not order more than can sell before expiry | Inventory days, overstock value | SDG 12.3 |
| Less manual work | Daily list replaces spreadsheet checking | Minutes per day, manual checks | Efficiency benefit |
| Better margin recovery | Discount before spoiling instead of dumping | Markdown recovery %, donation kg | SDG 12.5 |
| Safer food and clearer records | Batch traceability and approval log | Expired sales (target zero), audit completeness | SDG 2.1, 12.3 |
| Seasonal and local menu | Bakery advice uses in-season ingredients | Seasonal/local ingredient %, seasonal sales | SDG 2.4 |
| Lower emissions | Avoid waste and overproduction | Estimated kg CO2e avoided | SDG 13.2 |
| Community support | Safe surplus goes to donation partners | Kg donated, meals equivalent | SDG 2.1 |


Measure a baseline for two to four weeks before the pilot: waste, stockouts, expired stock, manager time, markdown recovery, and donations. Present the results as estimates with their assumptions, not guaranteed savings.

## Ease of learning

A new manager should get value in 15 minutes and finish the daily review in under 5 minutes.

- A guided first run with a sample shop and plain labels: “use first”, “buy now”, “bake plan”.
- One main daily screen. Every recommendation has a short “why”.
- Approve, edit, or reject in one click. Overrides need a short reason.
- A safe practice mode, undo, inline help, a glossary, and short videos.
- Different views for the owner, manager, baker, and shop staff.
- A 30-minute owner session, a 15-minute staff session, and a one-page quick card.
- A quick-start guide, daily routine, bakery guide, troubleshooting page, and glossary.
- Success measures: first useful recommendation in under 15 minutes, 80% of users complete the daily review without help, daily routine under 5 minutes, and support questions tracked.

## Where these sections go

- **Top of file:** “In one minute”, then “The SME problem”.
- **After Core Decision Logic:** “Automated workflow with human control”.
- **After the Bakery section:** “Orbyte fit and reuse”.
- **Inside SDG Alignment:** “Business benefit and SDG link”.
- **Before the timeline:** “Ease of learning”.

The existing sections stay intact. The 5-day plan only needs small notes: Day 1 agrees the problem, workflow, approval rules, and Orbyte fit; Day 3 adds benefit measures; Day 5 adds the learning guide and quick card.

## Start here for the working demo

- `docs/USER_GUIDE.md` — client, manager, and stakeholder guide, including the SDG link.
- `docs/DATA_IMPORT.md` — accepted CSV aliases, mixed date handling, the preview/commit API,
  and what an import writes.
- `docs/AB_TEST_PLAN.md` — store-week switchback design, primary metrics, guardrails,
  bootstrap confidence intervals, and the one-store limit.
- `docs/DEMO_SCRIPT.md` — the six-minute data-trust demo.
- `docs/EXPLAINER.md` — technical plain-English walkthrough.
- `docs/UI_DESIGN.md` — Autumn Bakehouse tokens, layout, motion rules, and the editable CSS scaffold.
- `IDEAS.md` — the weekly quest board plan, the decisions behind it, and what is shipped.
- `backend/README.md` and `forecast/README.md` — setup and engine details.

### Run the demo

The whole stack (API + dashboard) runs with Docker Compose:

```bash
docker compose -f backend/compose.yaml up -d --build
```

Then open the dashboard at <http://127.0.0.1:8501> and the API tester at
<http://127.0.0.1:8000/docs>. The API container seeds the fictional shop automatically on
first boot, so the dashboard has a full dataset: 8 suppliers, 16 products, 42 days of sales
history, live batches across every expiry bucket, and purchase orders in each workflow state.

To rebuild the demo data from scratch, drop the database volume and start again:

```bash
docker compose -f backend/compose.yaml down -v
docker compose -f backend/compose.yaml up -d --build
```

Without Docker, run the API and the dashboard in two terminals from the repository root:

```bash
cd backend && uv run python -m alembic upgrade head && uv run python -m scripts.seed && uv run python -m scripts.start
uv run streamlit run dashboard/app.py
```

For the data-trust demo, replace the seed command with
`uv run python -m scripts.seed --skip-history`, open **Settings → Import sales**, and load
`docs/samples/messy_sales.csv` or the generated sample. `--history-days N` controls how much
synthetic history the seed creates.
