# M1 API contract v0.1

Base URL: `http://127.0.0.1:8000/api/v1`; interactive tester: `/docs`; schema: `/openapi.json`.
All records in the demonstration are synthetic. This prototype has no authentication.
`actor_role` is a simulated business role, not a security credential.

## Endpoints

| Method | Path | Owner / behaviour |
|---|---|---|
| GET | `/health` (outside `/api/v1`) | M1: DB/schema readiness and business date. |
| GET, POST | `/suppliers` | M1: list/create. `include_archived=true` includes inactive suppliers. |
| GET, PUT, DELETE | `/suppliers/{id}` | M1: read/replace/archive. DELETE preserves referenced records. |
| GET, POST | `/products` | M1: list/create. `offset=0&limit=100`; maximum limit 2000. |
| GET, PUT, DELETE | `/products/{id}` | M1: read/replace/archive; units cannot change after stock receipt. |
| GET, POST | `/batches` | M1/M2: list/receive. POST writes both batch and opening movement atomically. |
| GET | `/batches/{id}` | M1: one batch. |
| PATCH | `/batches/{id}/status` | M1/M2: ACTIVE/QUARANTINED with role, reason and activity record. |
| GET | `/movements` | M1: read-only ledger, optional product_id, offset and limit. |
| POST | `/stock-actions` | M2: SALE/WASTE/DONATION hook. Returns 501 until implemented. |
| GET, POST | `/purchase-orders` | M1: list/create DRAFT. |
| GET | `/purchase-orders/{id}` | M1: PO plus lines. |
| POST | `/purchase-orders/{id}/approve` | M1: DRAFT -> APPROVED after simulated human decision. |
| POST | `/purchase-orders/{id}/cancel` | M1: cancel an unreceived DRAFT/APPROVED PO. |
| GET | `/products/{id}/on-order` | M1: future approved outstanding units; overdue shown separately. |
| GET | `/recommendations/{product_id}` | M3 calculation through M1 endpoint; 501 until connected. |
| GET | `/activity` | M1: recent approval/status events. |
| GET | `/exports/inventory.csv` | M1: downloadable batch inventory snapshot. |

## Shared conventions

- JSON field names use snake_case. IDs are integers. Dates are `YYYY-MM-DD`.
- UTC timestamps include a timezone. Business calendar dates use Asia/Kuala_Lumpur.
- Quantities support 3 decimal places; money supports 2. Each product has one fixed stock unit.
- Decimal values may be JSON strings, such as `"12.500"`. M5 converts explicitly for charts.
- List endpoints return arrays. Batches/movements/products have documented pagination.
- No endpoint directly overwrites remaining stock or edits/deletes ledger entries.
- Batch expiry date is an inclusive business date in this MVP; M2 defines and tests buckets.
- 200 success; 201 created; 204 archived; 403 disallowed simulated role; 404 missing record;
  409 duplicate/state conflict; 422 invalid input; 501 teammate service not implemented.

## M2 handoff

Replace `apply_stock_action(db, action, as_of)` in `app/services/stock_actions.py`.
`action` is `StockActionInput`: product_id, quantity, movement_type, daypart, request_id,
actor_name, actor_role, reason. The endpoint checks the simulated approval role.

Select ACTIVE, nonexpired, positive-quantity batches and allocate FEFO by expiry_date,
received_date, then id. Update remaining quantities and append one signed movement per
allocated batch in ONE transaction. A failed allocation must leave all batches unchanged.
Use request-level deduplication that supports multiple allocation rows; the existing unique
movement.request_id cannot be reused unchanged on every row of a multi-batch sale.
For example, introduce a stock_action_requests table through a new migration, with unique
request ID, canonical input and saved result, and link movements to that request.

The existing `receive_batch` is a minimal atomic receipt boundary. Extend/reuse it rather than
creating a second competing balance calculation. Every remaining balance must equal the sum
of its signed movements. Corrections are new adjustment movements.

Purchase-order receiving: update `received_quantity` and stock together. On-order is
`quantity - received_quantity` for APPROVED orders. Only mark RECEIVED when every line is
fully received. Partial receipt support is assigned to M2 and is not implemented here.

## M3 handoff

Replace `recommend(db, product_id, as_of)` in `app/services/recommendations.py`. Return:

```json
{
  "product_id": 1,
  "action": "HOLD",
  "quantity": "0.000",
  "rationale": "Current example; replace with the actual calculation",
  "confidence": 0.6,
  "expiry_risk": "warning",
  "forecast_horizon_days": 3
}
```

This example is a schema illustration, not a computed recommendation. The hook currently
raises NotImplementedError. Recommendations are read-only; applying one requires a separate
approved command. Read batches and stock movements through the supplied SQLAlchemy session.

Revisit the team's shelf-life cap when rounding to MOQ: rounding a capped quantity upward
can exceed the fresh-stock cap. Return HOLD/REDUCE or a clearly explained exception instead
of silently defeating that cap. Exclude overdue incoming orders from guaranteed supply.

M3 also owns documented SDG factors and unit-to-kg conversion. A loaf or litre is not
automatically one kilogram. Zero-valued seed factors must not be presented as real measurements.

## M4/M5 handoff

M4 owns the bakery policies. The draft bakery tables exist so the team can agree on schema.
No bakery forecasting or production endpoint is implemented by this M1 starter.

M5 calls HTTP endpoints from Streamlit with a timeout, checks `response.status_code` or
`response.raise_for_status()`, and presents errors. Display 501 as a pending integration,
not as a successful action. Use the response's returned IDs; do not assume IDs in an edited DB.

## API smoke test for M5

```python
import requests

BASE = "http://127.0.0.1:8000/api/v1"
response = requests.get(f"{BASE}/products", timeout=10)
response.raise_for_status()
products = response.json()
print(products)
```

`requests` belongs in the UI member's requirements if used. It is not needed by the M1 server.
