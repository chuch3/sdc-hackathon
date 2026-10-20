# Verification report

Verified in the execution environment on 2026-10-20, using Python 3.12.14 (Linux).

- 20 pytest tests passed, including migration from an empty database.
- Ruff lint and formatting checks passed.
- Initial Alembic migration, seed loading and OpenAPI export succeeded.
- Real Uvicorn HTTP checks returned 200 for health, docs, products and CSV.
- Seed fixtures reconcile every batch balance to its movement ledger.
- M2/M3 services are intentionally unimplemented integration hooks (HTTP 501).
- Windows command syntax is supplied; Windows and Docker execution were not performed here.

## Versions exercised

| Package | Version |
|---|---|
| fastapi | 0.141.1 |
| sqlalchemy | 2.0.55 |
| alembic | 1.20.0 |
| pydantic | 2.13.4 |
| pydantic-settings | 2.15.0 |
| uvicorn | 0.52.1 |
| pytest | 9.1.1 |
| httpx | 0.28.1 |
| ruff | 0.17.1 |
| tzdata | 2026.4 |
