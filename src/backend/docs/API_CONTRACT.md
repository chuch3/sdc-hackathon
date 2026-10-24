# API contract

Base URL: `http://127.0.0.1:8000/api/v1`; interactive tester: `/docs`; schema:
`/openapi.json`.

All records in the demonstration are synthetic. This prototype has no authentication.
`actor_role` is a simulated business role, not a security credential. Every write should
include `actor_name`, `actor_role`, and `reason`.

## Endpoints

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` (outside `/api/v1`) | DB/schema readiness, timezone, business date, and monotonic `data_version`. |
| GET, POST | `/suppliers` | List/create. `include_archived=true` includes inactive. |
| GET, PUT, DELETE | `/suppliers/{id}` | Read/replace/archive. DELETE preserves references. |
| GET, POST | `/products` | List/create. `offset=0&limit=100`; maximum 2000. |
| GET, PUT, DELETE | `/products/{id}` | Read/replace/archive; units cannot change after receipt. |
| GET, POST | `/batches` | List/receive. POST writes batch plus opening movement atomically. |
| GET | `/batches/{id}` | One batch. |
| PATCH | `/batches/{id}/status` | ACTIVE/QUARANTINED with role, reason, activity record. |
| GET | `/movements` | Read-only ledger; optional `product_id`, `offset`, `limit`. |
| POST | `/stock-actions` | FEFO SALE/WASTE/DONATION. Returns allocations and movements. |
| GET | `/stock-actions/{request_id}` | Replay a saved stock action result. |
| POST | `/stock-adjustments` | Signed manual adjustment recorded as a movement. |
| GET, POST | `/purchase-orders` | List/create DRAFT. |
| GET | `/purchase-orders/{id}` | PO plus lines. |
| POST | `/purchase-orders/{id}/approve` | DRAFT -> APPROVED after a simulated human decision. |
| POST | `/purchase-orders/{id}/cancel` | Cancel an unreceived DRAFT/APPROVED PO. |
| POST | `/purchase-orders/{id}/receive` | Partial or full receipt; creates batches and movements. |
| GET | `/products/{id}/on-order` | Approved outstanding units, with overdue shown separately. |
| GET | `/inventory/positions` | Saleable on-hand, on-order, risk, and allowed actions. |
| GET | `/expiry/buckets` | Expired/critical/warning/healthy totals. |
| GET | `/expiry/alerts` | Batches inside the near-expiry horizon. |
| POST | `/expiry/scan` | Record an expiry scan audit event. |
| GET | `/recommendations` | All active-product recommendations for a date, with `data_version`. |
| GET | `/recommendations/{product_id}` | One recommendation with calculation and forecast. |
| POST | `/recommendations/{product_id}/decision` | Approve/edit/reject and log the decision. |
| GET | `/planner/week` | Read-only seven-day projection: daily stock, arrivals, and action cards. |
| GET, PUT | `/bakery/profiles` | List/upsert bread profiles; bakery products only. |
| GET, POST | `/bakery/bake-plan` | Build/save a draft daypart bake plan. |
| POST | `/bakery/bake-plan/{product_id}/approve` | Approve the draft for a date. |
| GET | `/bakery/seasonal-advice` | In-season ingredient advice for the current month. |
| GET, POST | `/holidays` | List/create holiday calendar overrides. |
| GET | `/analytics/impact` | Estimated waste, donation, meals, and CO2e for `days`. |
| GET | `/analytics/proof` | Holdout accuracy, observed impact, annual run-rate, and assumptions for `days` (7–60). |
| GET | `/onboarding/readiness` | Data-trust stage, checks, usable/censored days, and the next action. |
| POST | `/imports/sales/preview` | Validate a JSON CSV payload and report row issues without writing. |
| POST | `/imports/sales/commit` | Import valid rows as closed historical batches, movements, and stockout markers; idempotent by `request_id`. |
| GET | `/analytics/activity-calendar` | One bucket per business day for the activity heatmap. |
| GET | `/integrations/orbyte` | Whether the optional Orbyte link is configured. |
| GET | `/activity` | Recent approval/status events. |
| GET | `/exports/inventory.csv` | Downloadable batch inventory snapshot. |

## Shared conventions

- JSON names use snake_case. IDs are integers. Dates are `YYYY-MM-DD`.
- UTC timestamps include a timezone. Business calendar dates use Asia/Kuala_Lumpur.
- Quantities support 3 decimal places; money supports 2. Each product has one fixed unit.
- Decimal values may be JSON strings, such as `"12.500"`.
- No endpoint overwrites remaining stock or edits/deletes ledger entries.
- Batch expiry is an inclusive business date. `days_to_expiry=0` is critical; negative is
  expired.
- 200 success; 201 created; 204 archived; 403 disallowed simulated role; 404 missing record;
  409 duplicate/state conflict; 422 invalid input.

## M2 inventory behaviour

`POST /stock-actions` accepts `product_id`, `quantity`, `movement_type`
(`SALE`/`WASTE`/`DONATION`), optional `daypart`, `request_id`, actor fields, and a reason.

- FEFO sorts eligible batches by `expiry_date`, `received_date`, then `id`.
- SALE and DONATION exclude expired and quarantined batches. WASTE may remove expired stock.
- Each allocated batch gets one signed movement linked to the same stock-action request.
- The request ID is idempotent. Repeating the same payload returns the saved result;
  reusing the ID with a different payload returns 409.
- A failed allocation leaves all batches unchanged. Short sales record a `stockout_events`
  row and return 409 with the available quantity.
- Adjustments are new signed movements; they never rewrite history.
- `receive_batch` and purchase-order receiving create the batch and movement in one
  transaction. Every remaining balance equals the sum of its signed movements.

## M3 forecast behaviour

`GET /recommendations` reads saleable stock, on-order supply, sales movements, and
`stockout_events` from SQLAlchemy, then calls the shared `forecast` package through
`FORECAST_PACKAGE_ROOT`.

- Stockout-censored days are excluded from demand history.
- The baseline forecaster is the fallback. ML is used only when configured and available.
- Recommendations are read-only. Applying one requires a separate stock action.
- Shelf-life caps are applied after safety stock. If rounding would exceed the cap, the
  recommendation stays at HOLD rather than silently over-ordering.
- Overdue purchase orders are not treated as reliable incoming stock.
- Zero-valued SDG factors are placeholders and must not be presented as measured impact.

## M4 bakery behaviour

Bakery products use profiles for maximum daily quantity and daypart shares. A bake plan
is always a draft until a manager approves it. Seasonal advice is advisory only. Bakery
logic stays behind policies; services do not branch on `if bakery`.

## M5 dashboard behaviour

The Streamlit dashboard calls HTTP only and never opens SQLite directly. It uses timeouts,
surfaces API errors, and shows estimates with their assumptions. The actor fields are
simulated roles; do not treat them as authentication.

## Data readiness and sales import

`GET /onboarding/readiness` is the source of truth for whether a forecast is trustworthy.
It uses a 28-day window and 14 usable days:

- `no_products` — no active products.
- `no_sales` — products exist but no usable sale days.
- `thin_history` — fewer than 14 usable days.
- `ready` — enough history and no sale today.
- `live` — ready, with a sale recorded today.

Days with a `StockoutEvent` are removed from that product's usable days, so one SKU's
empty shelf does not censor another SKU. `valid_days` is the union of usable product-days;
`censored_days` counts distinct censored dates. `next_action` names the page and label the
dashboard should offer.

`POST /imports/sales/preview` accepts `csv_text`, an optional `mapping`, and no file
upload. Required columns are date, SKU, and quantity; daypart and stockout are optional.
Auto-detection recognises `business_date`, `item_code`, `units`, `part_of_day`, and
`stock_out`, among other aliases. Mixed date formats are accepted and ambiguous values are
read day-first. The response reports valid, invalid, and duplicate rows, unknown SKUs,
usable days, and the first 50 issues. Preview never writes.

`POST /imports/sales/commit` adds `request_id`. A commit writes one closed
`IMPORT-HIST-{request_id}-{sku}` batch per SKU, one `RECEIPT` movement, dated `SALE`
movements, and one `StockoutEvent` per flagged row. It never touches saleable stock.
Reusing a request ID with the same payload replays the stored result; reusing it with
different CSV content returns 409. See `docs/DATA_IMPORT.md` for the full format.

## Live updates and proof

`data_version` is the maximum ID across the movement, batch, stockout, stock-action,
purchase-order, and activity tables. It changes whenever inventory or decision data
changes. The dashboard polls `/recommendations` and the activity feed on a 30-second
fragment and shows a changed-since card when the version moves.

`GET /analytics/proof?days=14` runs a single-cutoff holdout backtest over the shared
forecast package. It scores the last `days` completed business days, excluding today
because it is incomplete. It returns:

- `accuracy`: WAPE, bias, MAE, 80% interval coverage, observation count, excluded censored
  observations, and products evaluated.
- `observed`: sales, waste, donations, estimated CO2e/meals, and stockout events in the
  window.
- `projection`: annual run-rate of the observed window, explicitly not a causal claim.
- `assumptions`: method and factor caveats.

`GET /analytics/impact` honours `days` and filters `occurred_at` from the first instant of
the selected window.

## Decisions and the activity calendar

- `POST /recommendations/{product_id}/decision` records the decision in the activity log.
  `GET /recommendations` and `GET /recommendations/{product_id}` then return the most
  recent decision per product as `decision`, `decided_at`, and `decided_by`, so the
  dashboard can show what was already done instead of re-asking.
- `GET /analytics/activity-calendar?days=120` returns one bucket per business date with
  units sold, wasted, and donated, plus stockout and decision counts and a normalised
  `intensity` for the heatmap. `has_waste` and `has_stockout` mark the days that need a
  second look.

## Planner behaviour

`GET /planner/week` builds the weekly quest board. It never writes to the ledger.

- `start` must be after the business date and within 30 days of it; `days` is 1 to 14 and
  defaults to 7. Invalid values return 422.
- The week is projected day by day from the current state: arrivals, then sales, then
  end-of-day expiry. The shared FEFO allocator in `app/services/allocation.py` decides which
  batch a sale comes from, so the planner and `POST /stock-actions` never disagree.
- Demand comes from the forecast engine only. `SALE` movements are demand; receipts,
  waste, donations, and adjustments are not. Stockout-censored days stay excluded.
- Expired and quarantined stock is never projected as saleable. It becomes a `WRITE_OFF`
  card.
- Only `APPROVED` purchase orders arrive, on `expected_date`. Overdue approved orders
  arrive on the first day of the board and are flagged as overdue. Draft and cancelled
  orders are ignored.
- Money figures use batch unit cost, not retail price. They are cost-based estimates and
  the response states its assumptions in `assumptions`.
- The planner is deterministic: the same ledger state produces the same week.

## Operations-first additions

- `GET/POST /market-days`, `PUT/DELETE /market-days/{id}` manage one local market event per
  date. A market event has `market_date`, `label`, `demand_multiplier`, and `note`. Its
  multiplier is combined with any holiday multiplier and appears as `market_day` on the
  matching planner day.
- `GET /daily-sheet` is a read-only floor/bakery handoff payload. It groups today's expiry
  tasks, recommendations, approved deliveries, and bake plan; it never writes the ledger.
- `GET /purchase-orders/{id}/supplier-email-draft` returns an editable plain-text draft and,
  where the supplier has an email, a `mailto` URL. It does not send mail.
- `POST /webhooks/pos` accepts one JSON envelope with `event_id`, `event_type`,
  `occurred_at`, and `payload`. It requires Unix `X-Buns-Timestamp` and an
  `X-Buns-Signature` HMAC of `timestamp + '.' + raw body` using `POS_WEBHOOK_SECRET`.
  Sales use FEFO, stockouts are logged, and refunds are deliberately rejected until a manager
  identifies a safe batch. `event_id` is idempotent.

## Smoke test

```python
import requests

BASE = "http://127.0.0.1:8000/api/v1"
response = requests.get(f"{BASE}/products", timeout=10)
response.raise_for_status()
print(response.json())
```
