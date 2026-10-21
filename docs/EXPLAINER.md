# Plain-English Explainer

This document explains what this project is, how its pieces fit together, and what is
actually implemented today. It is a readable companion to `README.md`, not a replacement
for the detailed build plan.

## In one minute

This is a daily decision helper for a small bakery or food shop. Every morning it should
answer three questions:

1. What is about to expire, and what should we do with it?
2. What should we buy or bake, and how much?
3. What waste, stockout, or sustainability impact are we creating?

The system watches expiry dates, estimates what will sell, and recommends what to sell
first, discount, donate, buy, or bake. A person approves every action that costs money or
affects customers.

## What is in this repository today

The README describes the full intended system. The repository currently contains two
working pieces of it:

| Part | Status |
|---|---|
| `backend/` | FastAPI + SQLite API with FEFO stock actions, receipts, purchasing, expiry, recommendations, weekly planner, bakery, and impact endpoints |
| `forecast/` | Forecast and reorder engine, plus the optional ML challenger |
| `dashboard/` | Streamlit frontend for daily operations and the weekly quest board |
| `docs/` | Planning notes, this explainer, and the user guide |
| Root `README.md` | The 5-day build plan plus appended explanation sections |
| FEFO sales, bakery planning, SDG estimate reporting | Implemented as a demo; see caveats below |

The README's suggested `app/` layout is the plan. The actual backend lives in
`backend/app/`.

## The ELI5 flow

```text
Shop manager
   ↓ opens the Streamlit dashboard
FastAPI API
   ↓ checks the request
Services
   ↓ decide what to do
Policies
   ↓ generic shop vs bakery rules
SQLite database
   ↓ stores products, batches, and every stock movement
```

The core rule is simple: **you never edit stock directly**. Every quantity change should
be a row in `stock_movements`, so there is always a history of what happened.

## 1. The database is the source of truth

The important tables are in `backend/app/models.py`:

- **Supplier** — who delivers the goods.
- **Product** — what the item is, its shelf life, lead time, minimum order, allergens,
  and whether it is bakery or generic.
- **Batch** — a real delivery of a product, with its own expiry date and remaining
  quantity.
- **StockMovement** — an immutable ledger entry: receipt, sale, waste, donation,
  adjustment, or transfer.
- **PurchaseOrder** — what the shop plans to buy.
- **Bakery tables** — bread profiles, seasonal ingredients, and production plans.
- **ActivityEvent** — an audit record for approvals and status changes.

Why batches matter: two bottles of milk can have different expiry dates. The system
tracks them separately so the oldest can be sold first.

## 2. Receiving stock

The clearest existing flow is `receive_batch` in `backend/app/services/receipts.py:9`.

When a delivery arrives:

1. The API validates the data with Pydantic.
2. The service checks that the product exists and is active.
3. It checks the `request_id`. If the same request is sent twice, it returns the original
   batch instead of double-counting stock.
4. It creates the batch and its `RECEIPT` movement **in the same database transaction**.
5. It writes an activity event.

So either both the batch and the ledger row are saved, or neither is. That is the
"atomic" guarantee.

## 3. FEFO — what is supposed to happen when selling

FEFO means **First-Expired-First-Out**.

When someone sells 5 loaves, the system should:

1. Find batches that are active, not expired, and have stock.
2. Sort them by earliest expiry date.
3. Take stock from the oldest first.
4. Write one `SALE` movement per batch used.
5. Never allow expired stock to be sold.

This is implemented in `backend/app/services/stock_actions.py`. `POST /stock-actions`
allocates across batches, records one movement per batch, rejects expired or quarantined
stock, and replays the same `request_id` safely.

The decision of *which batch a unit comes from* lives in
`backend/app/services/allocation.py`. That module is pure: it sorts and splits quantities
without touching a database. The stock-action service does the writing; the weekly planner
reuses the same rules to project the week. One allocator, two callers, no drift.

## 4. Forecasting — guessing tomorrow's demand

The standalone engine is in `forecast/`. It does not write to the database and does not
change stock. It only calculates.

The default forecaster is `BaselineForecaster` in `forecast/baseline.py:69`.

In plain English:

- Look at the **last 28 days of sales** for this product.
- Ignore days marked as "stockout-censored", because a zero-sale day caused by an empty
  shelf is not real low demand.
- Take the average of the valid days.
- Multiply by factors:
  - weekday factor, such as Saturday being busier,
  - holiday or promotion multiplier,
  - bakery daypart share, such as morning versus afternoon.
- If the product is new and has fewer than 14 valid days, use the category average
  instead.
- If there is no usable history, mark the forecast as **not actionable**.
- Produce a range, a confidence label, reason codes, and a short "why" explanation.

Example:

```text
Expected demand: 40 loaves over 1 day.
Based on 22 valid days; 3 stockout days excluded.
Confidence is medium with variability 18%.
```

## 5. Reorder — turning a forecast into an action

`forecast/reorder.py:38` decides `BUY`, `BAKE`, `HOLD`, or `MARKDOWN`.

The maths, in words:

```text
Safety stock = how much buffer to keep for forecast error
Reorder point = expected demand + safety stock
Raw order = reorder point − saleable stock − already ordered
Fresh cap = what can realistically sell before it expires
Recommended = the smaller of raw order and fresh cap
```

Then it rounds up to the minimum order or case size.

Decision order:

1. If the forecast is blocked by missing or stale data, use **HOLD**.
2. If there is near-expiry surplus, use **MARKDOWN**.
3. If existing stock already covers demand, use **HOLD**.
4. If shelf life means fresh stock cannot sell, use **HOLD** and warn.
5. Otherwise, use **BUY** for normal products or **BAKE** for bakery products.

Every result includes a three-line rationale, a confidence level, expiry risk, the full
calculation, and `approval_required=True`.

Nothing is automatic. The system recommends; a human approves.

## 5b. The weekly planner — seven days in one read-only view

`GET /api/v1/planner/week` turns the forecast into a week-long board. It lives in
`backend/app/services/weekly_planner.py`.

The important part is that it does **not** ask the engine seven times. One forecast per
product is walked forward day by day:

```text
Start of day → receive due orders → sell what the forecast expects (FEFO)
            → expire what is left → record the day's stock and risk
```

Because the walk is forward-only, the cards do not repeat the same advice on every day,
and the stock on Tuesday already accounts for Monday's sales. The planner never writes to
the database: it is a projection, not an action. Expired and quarantined stock is never
projected as saleable, and only approved purchase orders are projected to arrive.

## 6. Bakery mode

Bakery is not a separate app. It is a **policy plugin**.

The interfaces live in `forecast/policies.py`:

- `DemandPolicy` — weekday, daypart, and seasonal factors.
- `PlanningPolicy` — should the answer be `BUY` or `BAKE`?
- `AdvicePolicy` — should this be marked down?

The generic and bakery implementations select different behaviour, so services do not
need `if bakery` scattered everywhere. The backend also exposes bakery profiles, bake-plan draft/approval, seasonal advice, and
holiday calendars. A baker saves a draft; a manager approves it.

## 7. The optional ML challenger

The ML model is in `forecast/ml/`. It is deliberately **not the boss**.

It predicts three numbers per day:

- `q10` — pessimistic demand,
- `q50` — expected demand,
- `q90` — optimistic demand.

The `q50` becomes the forecast, and `q10`–`q90` becomes the 80% range. The normal reorder
rules still apply afterwards.

It falls back to the simple rule-based forecaster when:

- the model file is missing,
- the product was not seen during training,
- sales history is missing or stale,
- there are fewer than 14 valid days.

A new ML model is only promoted to "champion" if:

- WAPE is not more than 1 percentage point worse than the baseline,
- bias stays within 10%,
- 80% coverage stays between 72% and 88%.

This is all demo-grade and trained on synthetic data, so the model card explicitly says
the numbers are not evidence of real-world accuracy.

## 8. Human approval and audit

The intended workflow is:

```text
Trigger → Data → Logic → Approval → Logged outcome
```

The default is **no action**. If nobody approves, nothing is bought, discounted, donated,
or baked.

The backend already supports parts of this:

- receipts require an actor and a reason,
- purchase orders are created as `DRAFT`,
- only an owner or bookkeeper role can approve,
- approvals and status changes create activity events,
- archived records are kept instead of deleted.

The role field is only a simulation; there is no authentication.

## 9. SDG and sustainability

The README maps the product to SDG 2, 12, and 13: less waste, better food access, and
lower emissions.

`GET /api/v1/analytics/impact` produces estimated waste, donation, meal, and CO2e totals.
The seed data has zero-valued placeholder factors, so those figures must not be presented
as real measurements. The Impact screen labels them as estimates and shows the assumption.

## 10. What is actually runnable today

From `backend/README.md`:

```text
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
```

That gives you the API at `/api/v1`, docs at `/docs`, and the full demo flow: products,
suppliers, batch receipts, FEFO sales, expiry buckets and alerts, purchase orders,
recommendations, bakery plans, and impact estimates.

The dashboard runs separately:

```bash
uv run streamlit run dashboard/app.py
```

The forecast demo runs separately:

```bash
uv run python -m forecast.cli --backtest
uv run python -m forecast.cli --forecaster ml
```

The browser app talks only to the API. The API imports the forecast package through
`FORECAST_PACKAGE_ROOT`, and the database remains the source of truth for stock.

## 11. Glossary

| Word | Plain meaning |
|---|---|
| **API** | The address another program calls to read or change data. |
| **Batch** | One delivery of a product with its own expiry date. |
| **FEFO** | First-Expired-First-Out: sell the oldest safe stock first. |
| **Ledger / movement** | An append-only record of every stock change. |
| **Saleable stock** | Stock that is active, not expired, and actually available to sell. |
| **MOQ** | Minimum order quantity the supplier will accept. |
| **Safety stock** | Buffer stock kept to cover forecast error. |
| **Reorder point** | Stock level that triggers a new order. |
| **Stockout-censored day** | A low-sales day caused by empty shelves, not by low demand. |
| **WAPE** | Weighted absolute percentage error; lower is better. |
| **Coverage** | How often the actual value falls inside the forecast range. |
| **Champion / challenger** | The current production model versus a candidate model. |

## Where to look next

- `docs/USER_GUIDE.md` — plain-language guide for shops, managers, and partners.
- `README.md` — the full build plan and business context.
- `backend/README.md` — setup steps for the working API.
- `backend/docs/API_CONTRACT.md` — endpoints and handoff notes.
- `forecast/README.md` — forecast inputs, outputs, and commands.
- `forecast/TODO.md` — what is done and what remains.
- `forecast/docs/ML_PLAN.md` and `forecast/docs/MODEL_CARD.md` — ML design and caveats.
