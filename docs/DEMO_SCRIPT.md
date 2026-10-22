# 6-minute demo script

## Before the room opens

```bash
cd backend
uv run python -m alembic upgrade head
uv run python -m scripts.seed --skip-history
uv run python -m scripts.start
```

In a second terminal from the repository root:

```bash
uv run streamlit run dashboard/app.py
```

Open <http://127.0.0.1:8501>. Keep `docs/samples/messy_sales.csv` on the desktop and a
second browser tab on the Impact screen.

## 0:00 — Name the real problem (45s)

"Small food shops do not lack data. They lack trust in the data they have. The system
refuses to guess, shows what it needs, imports the messy export, and then proves whether
its advice is accurate."

## 0:45 — Safe refusal on Today (60s)

- Today shows the **Data check** card, not confident recommendations.
- Point to: active products, usable sales days, required history, excluded stockout days.
- "No history means no pretend forecast. It tells us exactly what to import."

## 1:45 — Import the messy CSV (90s)

- Open **Settings → Import sales**.
- Download the sample, or click **Load the demo CSV**.
- Preview: six weeks of sales for every SKU; mixed dates are accepted; unknown SKUs and bad
  quantities are listed; duplicate rows are collapsed; stockout rows are marked.
- Import valid rows (the demo file has 675 data rows: 672 valid, 2 rejected, 1 duplicate).
- Return to **Today**. The readiness card moves to forecast-ready (or live if today's sales
  are present). The sample is long enough that the later proof has real history to score.
- "This wrote closed historical batches, not fake stock on today's shelf."

## 3:15 — Live loop (60s)

- Point to the **Live · updated HH:MM:SS · v...** strip and "auto-refreshes every 30s".
- Click **Simulate a sale**.
- The **Changed since the last check** card appears, the data version moves, and the
  recommendation and expiry numbers refresh without a manual reload.
- "Every change is still an immutable ledger movement."

## 4:15 — Impact proof (75s)

- Open **Impact**.
- Read the top proof cards: WAPE, bias, 80% coverage, observations, censored days excluded.
  With the checked-in sample and seed, expect roughly 12% WAPE and 80% coverage.
- Read observed waste/donations and the annual run-rate.
- "The backtest is evidence about forecast accuracy. Causality needs the switchback plan.
  We keep those claims separate."

## 5:30 — Close (30s)

- "The product is not a model demo. It is a data-trust loop: refuse, import, refresh,
  prove."
- One next step: pilot with one store for workflow usability, then a 4–8 store switchback.
- Mention `docs/AB_TEST_PLAN.md` for the statistical plan.

## Reset between runs

```bash
docker compose -f backend/compose.yaml down -v
docker compose -f backend/compose.yaml up -d --build
```

The container seeds the full 42-day dataset on first boot. Use `--skip-history` for the
data-trust opening.
