# Verification report

Core app verified on 2026-10-21; the data-trust phase was re-verified on 2026-10-22
(Linux, Python 3.11.12 root / 3.13 backend via `uv`).

## Automated checks

- `uv run pytest -q` (from `backend/`) — **70 passed**.
- `uv run pytest -q forecast/tests` — **45 passed**.
- `uv run ruff check backend dashboard forecast` — passed.
- `uv run python -m scripts.export_openapi` (from `backend/`) — regenerated
  `backend/docs/openapi.json`.
- Migration from an empty database and repeatable seed loading — passed.
- Every batch balance reconciles to its signed movement ledger.

## Data-trust flow

- Seeded with `--skip-history`, readiness reports `thin_history` with a link to import, and
  Today refuses to show a confident plan.
- Previewing `docs/samples/messy_sales.csv` reports 672 valid rows, 2 rejected rows, 1
  duplicate, 42 valid dates, and the unknown SKU without writing anything.
- Committing the sample creates 687 ledger movements and 1 stockout marker, leaves saleable
  stock unchanged, and moves readiness to `ready` with 16 of 16 products ready.
- Replaying the same `request_id` returns the stored result; different CSV content under the
  same ID returns 409.
- Readiness excludes stockout-censored days per product, so one SKU's empty shelf does not
  hide another SKU's usable history.
- The proof endpoint scores the last 14 completed days. After the sample import it reports
  about 12% WAPE and 80% interval coverage across 16 products.
- `data_version` moves on import and stock actions; the Today fragment shows the live strip
  and changed-since card.

## End-to-end checks

- Real Uvicorn HTTP checks returned 200 for health, inventory positions, expiry buckets,
  recommendations, bakery bake plan, seasonal advice, impact estimates, and Orbyte status,
  plus readiness, sales-import preview/commit, and proof.
- FEFO sale returned 201 with earliest-expiry allocations; expired and quarantined stock
  was excluded.
- Streamlit `AppTest` loaded Today, Inventory, Expiry, Recommendations, Purchasing, Bakery,
  Impact, and Settings with no script exceptions.
- Bakery draft save and manager approval succeeded through the dashboard client.
- Docker images for the API and dashboard built successfully.
- Docker compose auto-migrates and auto-seeds an empty demo volume; `/health` and
  `/api/v1/recommendations` returned 200 after a clean `down -v` and `up --build`.
- The dashboard follows the Autumn Bakehouse tokens in `docs/UI_DESIGN.md`; the bundled
  Fraunces and Nunito Sans fonts and all eight workspace screens loaded without exceptions.
- A headless Firefox session rendered every workspace screen against the Docker stack with
  the API connected (`http://api:8000/api/v1`), confirming sidebar navigation, primary
  button contrast, Altair charts, the animated Today hero, and the empty purchase-order state.
- A 920px-wide headless Firefox capture confirmed the responsive top navigation, hero layout,
  and active-navigation contrast.
- The ASCII Magic `autumn-forest` piece loaded from the CDN behind the workspace in its
  original autumn palette; navigating through all eight pages left exactly one script tag and
  one `<ascii-art>` element in the host page.
- The background is the library animation only; there is no pointer or click overlay.
- Background cost was reduced by rendering at a fixed 18px cell size and CSS-scaling to the
  viewport, lowering halftone density, and replacing the sticky-nav `backdrop-filter` with an
  opaque surface.
- `docker compose -f backend/compose.yaml up` served both health endpoints.

## Notes

- The ML path falls back to the rule-based baseline when no checkpoint exists.
- CO2e and meal figures use configured factors. The seed factors are placeholders, so the
  dashboard labels impact as an estimate.
- Windows command syntax is supplied in `START_HERE_WINDOWS.md`; Windows was not re-run here.
- The role selector is a simulation, not authentication.
