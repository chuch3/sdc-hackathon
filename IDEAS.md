# IDEAS.md — Weekly Quest Board and Week Simulation

This document records the plan for a Stardew-inspired weekly planner and week simulation.
It borrows the structure and feel of a game quest board, not any actual game assets.

> **Status (milestone 1 shipped):** the read-only weekly planner endpoint and the seven-day
> quest board page are implemented. The simulation engine is still planned. This document
> is the plan of record; the sections marked *Shipped* describe what exists today.

## Product concept

> A seven-day shop planner styled like a cozy game quest board. The forecast engine fills
> each day with small cards: "sell first", "mark down", "receive order", "buy", "bake",
> "hold". The manager can run the week forward and watch waste, stockouts, and savings
> change.

Two distinct features:

1. **Weekly plan** — a read-only forecast of the next seven days from the current backend
   state. **Shipped.**
2. **Week simulation** — execute those days using logged sales and approved purchase
   orders, updating a sandbox inventory. **Planned.**

The simulation must **not write to the live database**. Use a sandbox state or a separate
simulation database, then persist snapshots for replay.

## Decisions taken before implementation

| Question | Decision | Why |
|---|---|---|
| Scope of the first milestone | Planner endpoint plus the quest board page only | The projection engine and the shared allocator are the risky parts; the simulation needs both. |
| Visual style | Autumn Bakehouse theme, using the board structure from this document | One visual language in one app. No second stylesheet, no duplicated tokens. |
| Money | Cost-based estimates from batch unit cost; no retail price field | The data set has no retail price. Inventing one would put fabricated revenue in the demo. |
| Bakery | Bakery cards (`BAKE`) ship with the planner | The forecast package already returns `BAKE` for bakery products, so the card is a mapping, not new logic. |

### Corrections to the original plan

- **Do not add `backend/app/services/forecast_adapter.py`.** `forecast_repository.py`
  already adapts products, batches, sales-only history, stockout censoring, holidays, and
  the business timezone. Extend it instead.
- **Extract the FEFO allocator before building the simulator.** FEFO was embedded in
  `stock_actions.py` and coupled to the database. It now lives in
  `backend/app/services/allocation.py` as a pure module that both the stock-action service
  and the simulator call. `stock_actions.py` still owns the writes.
- **The planner projects day by day.** It does not call the pipeline once per day against
  current inventory; a seven-day projection needs one forecast and a forward walk
  (arrivals, then sales, then expiry) so the cards do not repeat.
- **Money is labelled.** Every figure is a cost-based estimate, stated in the response
  `assumptions` and in the UI.
- **Tests run per package.** `uv run pytest` at the repository root collects
  `forecast/tests`; the backend suite runs from `backend/` with `uv run pytest`.
- **`STOCKOUT` is an extra card kind.** The original list had no card for a projected
  shortage, so a day could be flagged risky with no action on it.

## Architecture

```text
backend SQLite
  products, batches, stock_movements, purchase_orders
        ↓
ForecastRepository (forecast_repository.py)
  reads sales + inventory + overrides
        ↓
ForecastPipeline / ReorderService
        ↓
Weekly planner service (weekly_planner.py)
  7 days × action cards, projected day by day
        ↓
Simulation engine (planned)
  receive orders → apply sales → expire stock → capture KPIs
        ↓
FastAPI endpoints
        ↓
Streamlit weekly quest board
```

## Data sources

### Sales

Use only `SALE` movements from `stock_movements`. Do not treat receipts, waste,
adjustments, or donations as demand.

For each sale:

- Convert `occurred_at` from UTC to the business timezone.
- Group by product, business date, and daypart.
- Mark stockout-censored days where demand exceeded available stock.
- Use the existing 35-day synthetic history as the initial replay source, or forecast
  future demand when no logs exist.

Two simulation modes:

| Mode | Sales source | Use case |
|---|---|---|
| **Replay** | Actual `SALE` logs for the selected week | Reliable, deterministic demo |
| **Forecast** | `ForecastPipeline` predictions plus a seeded demand draw | Future-week what-if |

Recommendation: support both, but default the demo to **replay** so the story is
repeatable.

### Orders

Use `purchase_orders` with status `APPROVED`.

- Arrival date = `expected_date`.
- Overdue approved orders arrive on day 1 with an "overdue" card.
- Draft and cancelled orders are ignored.
- On arrival, create a simulated batch with:
  - quantity = outstanding quantity,
  - expiry = arrival date + product shelf life,
  - unit cost from the PO line.
- Mark the simulated line received; mark the order received when fully delivered.

### Expiry and waste

At the end of each simulated day:

- Expired stock becomes waste or donation, never a sale.
- Near-expiry surplus becomes a markdown card.
- Safe surplus can become a donation card.
- Quarantined stock is excluded from saleable inventory.

Recommended daily order:

```text
Start of day → receive due orders → sales by daypart → end-of-day expiry actions → KPIs
```

This order matters and should be documented in the simulation engine. The shipped planner
uses the same order.

## Weekly plan contract

Shipped endpoint:

```http
GET /api/v1/planner/week?start=2026-10-19&days=7
```

`start` must be after the business date and within 30 days of it. `days` is 1 to 14 and
defaults to 7. Invalid values return 422. The response is read-only and deterministic.

Response shape:

```json
{
  "as_of": "2026-10-18",
  "start_date": "2026-10-19",
  "end_date": "2026-10-25",
  "day_count": 7,
  "mode": "forecast",
  "engine": "baseline",
  "generated_at": "2026-10-19T06:00:00Z",
  "days": [
    {
      "date": "2026-10-19",
      "weekday": "Monday",
      "headline": "Sell first: Sell or mark down 12 litres of Demo Fresh Milk.",
      "risk_level": "risky",
      "kpis": {
        "value_at_risk": "42.50",
        "expected_waste": "0.00",
        "stockout_risk": "low"
      },
      "cards": [
        {
          "kind": "SELL_FIRST",
          "priority": "critical",
          "product_id": 1,
          "product_sku": "MILK-001",
          "product_name": "Demo Fresh Milk",
          "quantity": "12.000",
          "unit": "litre",
          "deadline": "2026-10-19",
          "summary": "Sell or mark down 12 litre of Demo Fresh Milk before 2026-10-19.",
          "why": [
            "12 litre in stock expire on 2026-10-19.",
            "Expected sales on 2026-10-19 are only 8 litre.",
            "About 4 litre will not sell in time and will be written off."
          ],
          "confidence": 0.65,
          "expiry_risk": "critical",
          "impact": "Avoids about $30.00 of write-off (cost-based estimate).",
          "calculation": {
            "near_expiry_quantity": 12.0,
            "forecast_before_expiry": 8.0,
            "surplus": 4.0,
            "cost_at_risk": 30.0
          }
        }
      ],
      "orders_due": [],
      "projection": {
        "starting_stock": "20.000",
        "arrivals": "0.000",
        "expected_sales": "8.000",
        "unmet_demand": "0.000",
        "ending_stock": "12.000",
        "expired_quantity": "0.000"
      }
    }
  ],
  "badges": [],
  "weekly_summary": {
    "days": 7,
    "cards": 12,
    "cost_at_risk": "120.00",
    "expected_waste": "0.00",
    "estimated_cost_avoided": "60.00",
    "stockout_days": 0,
    "waste_free_days": 7,
    "plan_coverage_days": 6,
    "quest_progress": 0.8571
  },
  "assumptions": [
    "Money figures use batch unit cost, not retail price; treat them as cost-based estimates."
  ]
}
```

Card kinds:

| Kind | Meaning |
|---|---|
| `SELL_FIRST` | Stock expires soon; prioritise selling it. |
| `MARKDOWN` | Surplus is larger than expected sales before expiry. |
| `DONATE` | Safe surplus should go to a partner. |
| `WRITE_OFF` | Expired, quarantined, or unsafe stock; never sell. |
| `RECEIVE_ORDER` | Approved purchase order arrives. |
| `STOCKOUT` | Projected demand is larger than the projected saleable stock. One card per day, listing the products that run short and how long the gap lasts. |
| `BUY` | Reorder point breached for a generic product. |
| `BAKE` | Reorder point breached for a bakery product. |
| `HOLD` | No action needed. |
| `DATA_WARNING` | Stale, missing, or low-confidence data. |

Each card should have a standard three-line explanation:

```text
What:   Sell or mark down 12 litres of milk.
Why:    It expires today and only 8 litres are expected to sell.
Impact: Avoids about $30.00 of write-off (cost-based estimate).
```

The detailed calculation and confidence stay behind an expandable area.

## Simulation engine

Suggested endpoints:

```http
POST /api/v1/simulations
GET  /api/v1/simulations/{id}
POST /api/v1/simulations/{id}/advance
POST /api/v1/simulations/{id}/run
POST /api/v1/simulations/{id}/reset
```

Suggested request:

```json
{
  "start_date": "2026-10-19",
  "mode": "replay",
  "seed": 42
}
```

Internal state:

```python
SimulationState(
    run_id,
    current_date,
    mode,
    batches,
    on_order_lines,
    recommendations,
    events,
    kpis,
)
```

Per-day flow:

1. Load the current snapshot.
2. Receive approved orders due today.
3. Apply demand for each daypart using FEFO.
4. Record stockout quantities if demand exceeds saleable stock.
5. Expire, mark down, donate, or write off end-of-day stock.
6. Recompute the next day's recommendations.
7. Capture KPIs and events.
8. Save a snapshot.

Persistence options:

- **Recommended:** `simulation_runs` plus `simulation_snapshots` with JSON state. Simple,
  replayable, and keeps the live ledger untouched.
- Alternative: copy the SQLite file into a temporary sandbox and run the real services
  against it. More realistic, but slower and easier to get wrong.

Keep FEFO in one shared allocator module used by both the real stock-action service and the
simulator. Do not write a second allocation algorithm.

## UI design

### Layout

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Weekly quest board      Oct 19–25       Plan coverage  ███████░░░  │
│  Cost at risk $120.00 · Expected waste $0.00 · Cost avoided $60.00  │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬────┤
│ Monday   │ Tuesday  │ Wednesday│ Thursday │ Friday   │ Saturday │ Sun│
│ Oct 19   │ Oct 20   │ Oct 21   │ Oct 22   │ Oct 23   │ Oct 24   │    │
├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼────┤
│ [!] Milk │ [→] Bread│ [✓] Hold │ [↓] Milk │ [→] Order│ [★] Bake │ ...│
│ 12 L     │ arrives  │          │ markdown │ arrives  │ 118      │    │
│ expiring │ 40 loaves│          │ 8 L      │ 20 L     │ loaves   │    │
│ why...   │ why...   │          │ why...   │ why...   │ why...   │    │
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴────┘
```

### Visual language

The board lives inside the existing **Autumn Bakehouse** theme. The board structure is
inspired by a game quest board; the pixels are not.

- Parchment cards (`--paper`) on the existing warm canvas, not a separate wood theme.
- Fraunces for day and product names, Nunito Sans for body text, matching every other page.
- A colour-coded left edge per card kind, using the existing tokens: berry for write-off
  and stockout, amber for sell-first and bake, pumpkin for markdown, rust for buy,
  eucalyptus for arrivals, sage for donate.
- Day header with the weekday, the date, and a risk pill: calm, busy, risky.
- A plan-coverage progress bar and earned badges, both computed from the plan data.
- Small original SVG icons from `dashboard/art.py` for product categories.
- No Stardew Valley sprites or copied assets. The reference should be structural
  inspiration only.

### Card interactions

- Click the "Why" disclosure on a card to expand the reasoning, the impact, and the
  calculation.
- The board is read-only. Approve or edit the real action on the Actions page.
- Marking a card as done belongs to the simulation, which is not built yet.

### Responsive behaviour

- Desktop: seven columns.
- Tablet: Streamlit stacks the columns.
- Mobile: stacked days, one day per section.

### Streamlit approach

- `st.columns(7)` for the week board.
- Custom HTML/CSS inside each column for the cards.
- `st.session_state` for the active simulation run and selected day, once the simulation
  exists.
- `<details>` for the calculation.
- Keep the board HTML static and use Streamlit controls for actions. This is more reliable
  than trying to wire buttons inside raw HTML.

A custom React frontend would look better but would add setup and integration risk. For
this project, Streamlit plus custom CSS is the better trade-off.

## Gamification

Keep it light and business-relevant. The game layer should explain the work, not hide it.

### Quest progress

- Each day has three small quests:
  - Use or rescue near-expiry stock.
  - Receive or review incoming orders.
  - Review the forecast before closing the day.
- Completing a quest gives XP and moves the weekly progress bar.

### Badges

- **FEFO Apprentice** — completed a sale without touching expired stock.
- **Markdown Hero** — rescued surplus before it became waste.
- **Zero Waste Day** — no expired stock written off.
- **Stockout Slayer** — no stockout on a high-demand day.
- **Data Detective** — resolved a stale or missing-data warning.
- **Perfect Week** — completed all daily quests with no expired sales.

### Weekly report card

At the end of the simulation:

```text
Weekly Shop Report

Waste avoided:       6.2 kg
Stockouts prevented: 2
Cost avoided (est.): $84.20
Expired sales:       0
Plan completion:     86%
Grade:               A-
```

The money line is a cost-based estimate, not revenue, and it says so. Grade only the
simulation, and show the assumptions. Do not present it as a certified sustainability
result.

## Implementation plan

### Phase 1 — shared allocator and read-only planner (shipped)

1. ~~Add `backend/app/services/forecast_adapter.py`.~~ Superseded: `forecast_repository.py`
   already adapts the ledger to the forecast contracts.
2. ~~Extract the FEFO allocator.~~ Done as `backend/app/services/allocation.py`; the
   stock-action service now calls it and still owns the writes.
3. ~~Add `backend/app/services/weekly_planner.py`.~~ Done: it projects day by day and
   merges expiry risk, forecast, reorder recommendation, and order arrivals.
4. ~~Add `GET /api/v1/planner/week`.~~ Done, with response schemas and API tests.
5. ~~Add the dashboard week board page.~~ Done as `dashboard/views/week.py` in the
   Autumn Bakehouse theme, with plan coverage, badges, and expandable "why" areas.

### Phase 2 — simulation engine (next)

6. Add `backend/app/services/simulation.py`.
   - In-memory state loaded from the backend.
   - Receive orders, apply sales, expire stock, compute KPIs.
   - Deterministic with a seed.
   - Uses `allocation.py` for every allocation, so the sandbox and the ledger agree.
7. Add `simulation_runs` and `simulation_snapshots` models and migration.
8. Add simulation endpoints.
9. Add tests for order arrival, FEFO, stockouts, expired stock, and no live-DB writes.

### Phase 3 — simulation in the board

10. Add day-by-day advance and run controls to the quest board.
11. Add the weekly report card and quest completion.
12. Keep the board read-only until a run is started.

### Phase 4 — polish

13. Add "Judge Mode" reset and scripted scenario.
14. Add responsive layout and empty/error states.
15. Add a demo narrative and screenshots.

## Testing

Shipped in `backend/tests/test_allocation.py` and `backend/tests/test_planner.py`:

- The allocator orders by expiry, then receipt, then id, and never oversells.
- Expired and quarantined stock are excluded from saleable candidates.
- Planner returns seven days and stable card ordering.
- Sales come only from `SALE` movements.
- Draft POs never arrive.
- Approved POs arrive on the expected date.
- Overdue POs arrive on day 1.
- FEFO consumes the earliest expiry first.
- Expired and quarantined stock cannot be sold and become write-off cards.
- Demand above available stock records a stockout, not negative inventory.
- The planner never writes to the live ledger.
- The same state produces the same week.

Still open for the simulation:

- The same seed produces the same simulated week.
- Every simulated quantity change has a simulated movement.
- Cards include a reason, confidence, and calculation.
- UI shows a pending-integration message if an endpoint returns 501.

## Guardrails

- Simulation is a sandbox; real stock changes still require real approvals.
- Expired food can never be sold, even in the simulation.
- Every simulated quantity change should have a simulated movement.
- Do not use Stardew Valley assets; create an original visual style.
- Label SDG, CO2e, and money figures as estimates with assumptions.
- Money in the planner is a cost-based estimate until a retail price exists.
- Do not let gamification imply that food-safety decisions are optional.
- Keep the planner deterministic for demos.

## Open questions

1. **Simulation source:** replay a past week from sales logs, simulate a future week from
   forecasts, or support both?
   Recommended: both, with replay as the default demo mode.

2. **Simulation persistence:** sandbox snapshots in SQLite, or a temporary cloned database?
   Recommended: sandbox snapshots; safer and easier to reset.

3. **Gamification depth:** light badges only, or a full XP/quest/report-card system?
   Recommended: light quests, badges, and a weekly report card. Enough to be fun without
   distracting from the business value. The board ships with badges and plan coverage
   only; XP arrives with the simulation.

4. **Visual assets:** original CSS/SVG pixel art, or borrowed open-license pixel assets?
   Recommended: original CSS/SVG, so there are no licensing questions.

## Milestone status

- [x] Shared FEFO allocator with regression tests.
- [x] `GET /api/v1/planner/week` with a day-by-day projection and action cards.
- [x] Seven-column quest board in the Autumn Bakehouse theme.
- [ ] Week simulation: models, migration, engine, endpoints, and board controls.

