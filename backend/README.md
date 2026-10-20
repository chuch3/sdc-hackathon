# M1: start here

**Windows quick start:** read [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md).
After extracting the GitHub ZIP and installing Python, double-click `START_WINDOWS.cmd`.
Keep its window open, then visit `http://127.0.0.1:8000/docs` after startup completes.

You are building the database and the HTTP API for the Perishable Food Inventory team.
This starter implements the M1 foundation and includes explicit connection points for M2 and M3.

The intended flow is:

```text
M5 Streamlit screen -> your FastAPI endpoint -> service -> SQLAlchemy -> SQLite file
```

The five words you need first:

| Word | Meaning in this project |
|---|---|
| Backend | The Python program that validates requests and reads/writes records. |
| Database | `data/inventory.db`, the SQLite file holding the demo records. |
| API endpoint | An address such as `/api/v1/products` that another program can call. |
| Model | A Python class describing a database table, in `app/models.py`. |
| Migration | A versioned database-structure change, managed by Alembic. |

## What is already implemented

- FastAPI application with interactive `/docs` and a `/health` check.
- SQLAlchemy models and an initial Alembic migration for the shared tables.
- Supplier/product create, read, update, and archive endpoints.
- Batch receipt with validation, a matching stock-ledger entry, and request deduplication.
- Batch quarantine/reactivation with a recorded reason.
- Read-only movement and activity history.
- Purchase-order drafts, human-approved status, cancellation, and on-order quantities.
- Inventory CSV export, relevant database indexes, and OpenAPI export.
- Repeatable fictional seed data and automated tests.
- Optional container configuration, architecture notes, and teammate contracts.

## What your teammates still implement

| Owner | Remaining work / connection point |
|---|---|
| M2 | FEFO sale/waste/donation actions, adjustments, expiry buckets and safe action rules. Replace `app/services/stock_actions.py`; extend the existing receipt service if needed. |
| M3 | Forecasts, reorder calculations, confidence, and SDG metrics. Replace `app/services/recommendations.py`. |
| M4 | Bakery strategy/policies, bakery endpoints, bake plans, seasonal advice. Bakery tables are included as a starting agreement, not completed business logic. |
| M5 | Streamlit screens, HTTP client, full-team QA, slides and demonstration. |

The M2/M3 endpoints return **501 Not Implemented** until the relevant service is connected.
They do not invent successful sales or recommendations. Authentication is intentionally absent;
the actor-role fields are a simulation for the local prototype.

## Step 1: install/check your tools (Windows)

Install Python **3.12**, VS Code, and Git if they are missing. Use the official installers.
Open PowerShell and run these separately:

```powershell
py --version
git --version
```

You should see a Python version and a Git version. If `py` is not recognised, install Python
with the Windows launcher enabled, reopen PowerShell, and try again. Python 3.11+ is the
team requirement; the starter was exercised using Python 3.12.

## Step 2: open the right folder

Extract the ZIP. Open the extracted `m1-backend-starter` directory in VS Code using
**File -> Open Folder**. In VS Code choose **Terminal -> New Terminal**, then select PowerShell.

Run:

```powershell
Get-ChildItem
```

You should see `app`, `scripts`, `tests`, `requirements.txt`, and `alembic.ini`.
Every command below assumes this is your current directory.

If your team already has a shared repository, introduce these files on an M1 branch and
review overlapping files before merging. Coordinate with M4 before changing the bakery schema.

## Step 3: create an isolated Python environment

```powershell
py -3.12 -m venv .venv
```

This creates a `.venv` directory for this project's packages. If you installed Python 3.11,
use `py -3.11 -m venv .venv` instead.

The commands use the environment's Python directly, so you do not need to activate it or
change PowerShell's execution policy.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Wait for installation to finish. In VS Code, run **Python: Select Interpreter** from the
command palette and choose this folder's `.venv` interpreter if the Python extension is installed.

## Step 4: create your local settings

For the first setup:

```powershell
Copy-Item .env.example .env
```

Open `.env`. The defaults are sufficient:

```dotenv
DATABASE_URL=sqlite:///./data/inventory.db
BUSINESS_TIMEZONE=Asia/Kuala_Lumpur
APP_NAME=Perishable Food Inventory - M1 Backend
```

SQLite runs inside Python. There is no separate database server to install or sign into.
All members use the same timezone convention. `tzdata` is included for Windows timezone support.

## Step 5: create the database tables

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

This applies the included migration and creates `data/inventory.db`.

```powershell
.\.venv\Scripts\python.exe -m alembic current
```

Expected: the included revision identifier marked as the current head.
Use Alembic for future shared schema changes; restarting FastAPI does not migrate a database.

## Step 6: load the fictional demo records

```powershell
.\.venv\Scripts\python.exe -m scripts.seed
```

Expected: 3 suppliers, 4 products, 80 batches, and 35 days of synthetic transaction history.
Most historical batches are closed; current examples include near-expiry, expired and
quarantined stock. Every batch quantity reconciles to its ledger.

Running seed again prints `Demo data already loaded; nothing changed.` It does not reset stock.
Dates are relative to the current Kuala Lumpur business date. A fixed test date is optional:

```powershell
.\.venv\Scripts\python.exe -m scripts.seed --as-of 2026-10-20
```

Use a new empty demo database for a different seed date. M3 can extend the history generator.
The SDG factors are explicitly zero-valued placeholders; M3 must add documented factors
and weight conversions before reporting estimated environmental impact.

## Step 7: start your API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Keep this terminal open. Uvicorn should report that it is running at `http://127.0.0.1:8000`.
Open these browser addresses:

- `http://127.0.0.1:8000/health` — should contain `"status":"ok"` and `"schema":"ready"`.
- `http://127.0.0.1:8000/docs` — the interactive API testing page.
- `http://127.0.0.1:8000/api/v1/products` — a JSON list containing the four seeded products.

Press **Ctrl+C** in the server terminal to stop it. Re-run the Uvicorn command to start again.

## Step 8: learn GET and POST in the browser

On `/docs`, expand **GET /api/v1/products**, click **Try it out**, then **Execute**.
The response code should be **200** and show product records.

Next expand **POST /api/v1/suppliers**, click **Try it out**, and replace the example body with:

```json
{
  "name": "Fictional Demo Supplier Two",
  "lead_time_days": 2,
  "moq": "5.000",
  "reliability": "0.950"
}
```

Click **Execute**. Expect **201 Created** and an `id`. Write down that returned ID.
IDs identify records; use the actual values returned by your database.

## Step 9: create your first product

Use **POST /api/v1/products** with:

```json
{
  "sku": "DEMO-MILK-NEW-001",
  "name": "Fictional Demo Milk",
  "category": "dairy",
  "unit": "litre",
  "shelf_life_days": 7,
  "storage_type": "chilled",
  "supplier_id": 1,
  "lead_time_days": 2,
  "moq": "5.000",
  "safety_stock_days": "1.000",
  "allergens": ["milk"],
  "seasonal": false,
  "domain": "generic"
}
```

Use an existing supplier ID. Record the new product ID from the **201** response.
Each SKU must be unique. A second creation with the same SKU should produce **409**, which
shows duplicate protection working.

## Step 10: receive a batch and verify the ledger

Use **POST /api/v1/batches**. Replace `product_id` with your returned product ID and use
today's date plus a valid future expiry date. The following dates are only an example:

```json
{
  "actor_name": "Demo Owner",
  "actor_role": "owner",
  "reason": "Owner approved the fictional delivery",
  "product_id": 1,
  "batch_code": "MANUAL-DEMO-001",
  "quantity_received": "12.500",
  "received_date": "2026-10-20",
  "baked_date": null,
  "expiry_date": "2026-10-25",
  "unit_cost": "3.20",
  "request_id": "manual-receipt-001"
}
```

Expect **201**, with `quantity_remaining` equal to `12.500`.
Use **GET /api/v1/movements** and filter by that product ID. You should find one new
`RECEIPT` movement with `quantity_delta` equal to `12.500`.

Execute the identical receipt again: it should return the same batch without adding stock.
Changing the quantity while reusing `request_id` should produce **409**. A genuinely new
receipt needs a new batch code and request ID.

There is deliberately no request field for directly setting `quantity_remaining`.
M2's services must change stock and add movements together.

## Step 11: test a purchase order (Day 3 work)

Use **POST /api/v1/purchase-orders**:

```json
{
  "supplier_id": 1,
  "expected_date": "2026-10-23",
  "lines": [
    {"product_id": 1, "quantity": "20.000", "unit_cost": "3.20"}
  ]
}
```

Replace the expected date with tomorrow or later and use your actual IDs.
The returned status is `DRAFT`. Draft quantities do not count as incoming stock.

Use **POST /api/v1/purchase-orders/{order_id}/approve** with the returned order ID:

```json
{
  "actor_name": "Demo Owner",
  "actor_role": "owner",
  "reason": "Reviewed and approved the demo purchase"
}
```

Expect `APPROVED`. Then use **GET /api/v1/products/{product_id}/on-order**.
That quantity should now include the approved order. No actual supplier order or payment is sent.
Overdue deliveries are reported separately so M3 does not treat a missed delivery as reliable supply.

M2 must connect purchase-order receiving later: record the receipt, update the line's
`received_quantity`, and mark a fully received PO in the same transaction. This starter does
not expose a shortcut that marks goods received without adding stock.

## Step 12: run the automated checks (a second terminal)

Leave the server running. Open another terminal in the same folder and run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

The tests use temporary databases, not your demo file. Checks include ledger balancing,
duplicate receipts, invalid dates, archived records, approval roles, purchase-order quantities,
CSV, the M3 integration boundary, and migrating an empty database.

If a test fails, read the final error and the named test. Reproduce that scenario in `/docs`.
Do not remove a failing test merely to make the display green.

## Step 13: hand your teammates a stable API contract

Share `docs/API_CONTRACT.md`. Export the machine-readable version:

```powershell
.\.venv\Scripts\python.exe -m scripts.export_openapi
```

That writes `docs/openapi.json`. Share this note with the team:

> API base: http://127.0.0.1:8000/api/v1. Interactive tester: /docs.
> M2: implement app/services/stock_actions.py using the shared models/session.
> M3: implement app/services/recommendations.py returning Recommendation.
> M4: coordinate bakery model changes through Alembic.
> M5: use HTTP requests; do not open or edit SQLite from Streamlit.

`127.0.0.1` means the computer running the request. Each teammate can run their own copy
with their own synthetic database. For the simplest integrated demonstration, run FastAPI
and Streamlit on the same laptop. Commit code and migrations, not SQLite or `.env` files.

## Step 14: make later schema changes properly

Agree on the field with the affected teammate. Edit the SQLAlchemy model, then:

```powershell
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "add agreed field"
```

Open the generated file in `migrations/versions`. Check that it changes only the agreed
tables/fields and preserves existing data. Adding a required field to a populated table
needs a backfill/default plan; autogeneration does not decide that for you.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
```

Commit the model and migration together. Teammates run `alembic upgrade head` after pulling.
Pick one person to coordinate migration numbering to avoid two competing migration heads.

## Step 15: your five-day checklist

| Day | Your concrete tasks | Show the team |
|---|---|---|
| 1 | Run the starter, understand models/schemas, confirm units and dates with M2/M3/M4, freeze the API contract, introduce files on an M1 branch. | `/health`, products, migrated database, repeatable seed. |
| 2 | Exercise supplier/product updates, batch receipts, validation, duplicate requests, ledger and archive behaviour. Connect M2's service with M2. | Receive stock, then M2's sale deducts stock and creates matching movements. |
| 3 | Exercise draft/approved/cancelled POs and on-order. Connect M3's recommendation function; return the agreed response schema. | A real M3 calculation comes through your endpoint with its rationale. |
| 4 | Run clean-database tests, check FEFO indexes with M2, export CSV, fix M5 integration problems. Docker is optional. | A new checkout can migrate, seed, serve, and pass the team's checks. |
| 5 | Finalise `docs/ARCHITECTURE.md`, API examples and deployment instructions. Fix bugs and rehearse your explanation. | Explain schema, API validation, ledger invariants and migration process. |

Commit small tested changes. Everyone tests their own services; M5 coordinates full-system QA.

## Put your work in the team's GitHub repository

For a new greenfield repository, create an empty GitHub repository in your account/team and
copy its HTTPS repository URL. Run these in the extracted project directory:

```powershell
git init
git add .
git status
git commit -m "Add M1 backend foundation"
git branch -M main
git remote add origin YOUR_ACTUAL_GITHUB_REPOSITORY_URL
git push -u origin main
```

Replace the URL placeholder before running the remote command. GitHub may ask you to sign in.
`git status` should show source files, never `.env`, `.venv` or `data/inventory.db`.
If Git asks for your name/email, use your own Git identity and retry the commit.

For an existing shared repository, use its checkout and create an M1 branch:

```powershell
git switch -c m1-backend-data
git add .
git status
git commit -m "Add M1 backend foundation"
git push -u origin m1-backend-data
```

Open a pull request in GitHub and have one teammate review it. Later changes should use
short branches and include the tests/migrations affected by the change. M5 can add
`dashboard/` to this same repository.

## Optional Docker, after local setup works

If Docker Desktop is already installed and running:

```powershell
docker compose up --build
```

In another terminal:

```powershell
docker compose exec api python -m scripts.seed
```

The database is persisted in a named Docker volume. This is separate from your local
`data/inventory.db`. Use `docker compose down` to stop containers while retaining data.
Container execution depends on your Docker installation; the ordinary Python setup is sufficient.

## Common problems

| Symptom | What to do |
|---|---|
| `No module named fastapi` | Run installation with `.\.venv\Scripts\python.exe`, then start with that same interpreter. |
| `no such table: products` or health 503 | Run `alembic upgrade head` from the project folder. |
| Empty product list | Run seed against the same `DATABASE_URL` used by the server. |
| 422 response | Read the response's `detail`; check required fields, numeric values and date format `YYYY-MM-DD`. |
| 409 response | Check duplicate SKU, batch code or request ID, or a disallowed state transition. |
| 403 response | The simulated actor role cannot approve that action. |
| 501 on stock-actions or recommendations | The M2 or M3 service is intentionally not connected yet. |
| Address/port already in use | Stop the earlier Uvicorn terminal with Ctrl+C. Alternatively use `--port 8001` and update the UI's API base. |
| SQLite database locked | Stop duplicate writers, keep transactions short, and ask M2 to review transaction boundaries. |
| A teammate's `localhost` cannot reach your API | Run both services on one demo laptop, or each member runs their own backend copy. |

Your first checkpoint is simply: **start -> migrate -> seed -> open /docs -> create a product
-> receive a batch -> inspect its movement**. Understand that loop before connecting forecasts.
