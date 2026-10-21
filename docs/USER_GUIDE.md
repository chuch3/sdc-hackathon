# FreshStock guide for shops, managers, and partners

This guide explains what the system does, how to use it in a normal working day, and
how it connects to the UN Sustainable Development Goals. It is written for a shop owner,
manager, baker, or community partner, not for a software engineer.

## What it does

FreshStock helps a small food shop or bakery answer four questions every morning:

1. **What will expire soon?**
2. **What should we sell first?**
3. **What should we buy or bake?**
4. **What did we save from waste, and what did we give to the community?**

It watches batches and expiry dates, estimates demand, and suggests an action. A person
always makes the final decision. Nothing is bought, discounted, donated, or baked without
approval.

## The one rule that keeps food safe

**Food is always sold or used oldest-expiry first.** This is called FEFO, or
First-Expired-First-Out.

The system checks every batch before it is used:

- expired batches are never sold,
- quarantined batches are never sold,
- the batch closest to expiry is used first,
- every quantity change is written to a permanent record.

If a batch cannot be used, it can be recorded as waste with a reason. Safe surplus can be
recorded as a donation. The system keeps the history.

## A five-minute daily routine

### 1. Start on **Today**

The Today screen shows the most urgent work:

- how many units are close to expiry,
- how many products need a decision,
- the estimated waste avoided so far,
- a short list of actions for the day.

If the screen says **API not ready**, ask an administrator to start the backend. Do not
enter stock in a spreadsheet in the meantime; that would break the audit trail.

### 2. Check **Expiry**

The Expiry screen groups batches by urgency:

| Group | What it means | Usual action |
|---|---|---|
| **Expired** | Past the safe date | Write off or dispose; never sell |
| **Critical** | Expires today or tomorrow | Sell first, mark down, or donate |
| **Warning** | Expires soon | Move to the front, plan a promotion |
| **Healthy** | Plenty of shelf life left | Leave it |

Sell the critical items first. If the item will not sell in time, mark it down or donate it
before it becomes waste.

### 3. Review **Recommendations**

Each recommendation has a plain-language reason and a suggested action:

- **Buy** — order more from the supplier.
- **Bake** — make more in the bakery.
- **Hold** — current stock is enough.
- **Markdown** — reduce the price to sell near-expiry stock.
- **Donate** — send safe surplus to a partner.
- **Write off** — record unavoidable waste.

The screen shows the expected demand, the confidence, and what is already on order. You
can approve, edit, or reject. If you edit, record why. The original suggestion is kept.

Once you decide, the card keeps the outcome: it shows an **Approved**, **Edited**, or
**Rejected** label with your name and the time, so the same decision is never asked twice.

### 4. Use **Purchasing**

Purchase orders are created as drafts. A manager approves them before they are sent. When
a delivery arrives, record the actual quantity and expiry date so the batches are correct.

Do not approve an order just because the system suggests it. Check the supplier, the
delivery date, and whether similar stock is already on its way.

### 5. Look ahead on **Week board**

The Week board is a seven-day plan built from today's stock, the approved orders, and the
forecast. Each day shows the projected stock, what arrives, and a short list of cards:
sell first, markdown, buy, bake, receive order, write off, or stockout.

- Hover a card to see why it is there. On a touch screen, use **Expand every card**.
- Under the board, the **activity calendar** shows how busy each day was. A red corner
  means stock was wasted that day; an amber corner means a stockout was recorded.

Two things to remember:

- The board is **read-only**. It shows what the forecast expects; it does not change stock.
  Approve the real action on **Recommendations** or **Purchasing**.
- The money on the board is a **cost-based estimate** built from what the shop paid, not
  from selling prices.

### 6. Plan the bakery on **Bakery**

The Bakery screen splits the daily bake into morning, midday, and afternoon. It respects
the maximum daily quantity and the shop's usual daypart mix. A baker can save a draft; a
manager approves the plan.

Seasonal advice shows which ingredients are in season and locally available. Treat it as
a suggestion, not a rule.

### 7. Show the result on **Impact**

The Impact screen estimates:

- kilograms of food waste,
- kilograms donated,
- meals provided,
- kilograms of CO2e avoided.

These are **estimates**. They use simple conversion factors and should be presented with
their assumptions. They are not audited carbon accounting or certified SDG results.

## Roles and approvals

The demo uses a role selector instead of real login.

| Role | Can do |
|---|---|
| **Owner** | Everything, including approvals |
| **Manager** | Approve purchases, markdowns, donations, and bake plans |
| **Bookkeeper** | Approve money-related actions |
| **Baker** | Prepare and save bake plans |
| **Staff** | Record sales through FEFO |
| **Viewer** | Read-only |

In a real shop, connect these roles to your existing identity system. Do not share one
login.

## How the recommendation is calculated

In plain words:

```text
Expected demand  = recent sales, adjusted for weekday and holidays
Safety stock     = a buffer for forecast error
Reorder point    = expected demand + safety stock
Raw order        = reorder point - saleable stock - stock already on order
Fresh cap        = what can realistically sell before it expires
Suggestion       = the smaller of raw order and fresh cap, rounded to case size
```

Days with empty shelves are treated as **stockout days**, not as days with low demand.
This prevents the system from wrongly ordering less after a busy day when it ran out.

If there is not enough history, the system says so and falls back to a safe rule-based
forecast. It does not pretend to be confident.

## UN SDG link

The system supports, but does not replace, a shop's own sustainability reporting.

| SDG target | What the shop does | What to measure |
|---|---|---|
| **SDG 2.1** — safe, nutritious food access | Keep shelves stocked; donate safe surplus | Availability, donation kg, meals |
| **SDG 2.4** — sustainable food production | Use seasonal and local ingredients | Seasonal/local ingredient share |
| **SDG 12.3** — halve food waste | FEFO, expiry alerts, demand-based buying and baking | Waste kg, expired stock value, waste rate |
| **SDG 12.5** — waste prevention | Mark down or donate before spoiling | Kg diverted from waste, markdown sell-through |
| **SDG 13.2** — climate action | Avoid overproduction and waste | Estimated kg CO2e avoided |

**Important:** report these as *estimated contributions*. Show the baseline, the
conversion factors, and the assumptions. Do not claim certified SDG impact.

## Orbyte

Orbyte is an HR and leave-management portal. It does **not** expose public inventory or
product endpoints, so it should not be the place where stock is entered.

A sensible integration is:

- launch the FreshStock dashboard from Orbyte,
- pass the signed-in person's name and role,
- keep inventory, purchases, and approvals in FreshStock,
- send approval notifications back to Orbyte if needed.

The backend exposes `GET /api/v1/integrations/orbyte` so the dashboard can show whether
an Orbyte link is configured. Credentials belong in environment variables, never in code.

The dashboard uses the Autumn Bakehouse theme: Fraunces and Nunito Sans, a warm cream
canvas, rust and amber accents, navigation across the top of the page, and a vintage
letterpress treatment (aged paper, double rules, small-caps labels, stamp-style status chips).
The workspace panel is opaque, so the data always sits on solid paper, and the animated
**Autumn Forest** piece from ASCII Magic sits behind it as the page background. The piece is
decoration only; if it cannot be fetched the aged-paper background remains and the dashboard
still works. The design tokens, layout, and the editable CSS scaffold
(`dashboard/static/theme.css`) are documented in `docs/UI_DESIGN.md`.

## Running the demo

From the repository root:

```bash
uv sync
cd backend
uv run python -m alembic upgrade head
uv run python -m scripts.seed
uv run python -m scripts.start
```

In a second terminal, from the repository root:

```bash
uv run streamlit run dashboard/app.py
```

Open `http://localhost:8501`. The API documentation is at `http://127.0.0.1:8000/docs`.

To reset the demo, stop the API, delete `backend/data/inventory.db`, and run the migration
and seed again. Never do this with live shop data.

## What is still a demo

- The role selector is not authentication.
- The seed data is fictional.
- CO2e and meal factors are zero or illustrative unless the shop configures real values.
- The forecast is trained on synthetic data; its accuracy is not evidence of real-world
  accuracy.
- Some advanced reports (rolling backtests, full approval expiry, automated purchase
  sending) are still future work.

## Glossary

| Word | Plain meaning |
|---|---|
| **Batch** | One delivery of a product, with its own expiry date. |
| **FEFO** | First-Expired-First-Out: use the oldest safe stock first. |
| **Saleable stock** | Stock that is active, not expired, and available to sell. |
| **Stockout day** | A day with low sales because the shelf was empty. |
| **Safety stock** | A buffer kept for forecast error. |
| **Reorder point** | The stock level that triggers a new order. |
| **MOQ** | Minimum order quantity the supplier accepts. |
| **Case size** | The pack size used when rounding an order. |
| **Confidence** | How much history supports the forecast; not a guarantee. |
| **Waste rate** | Waste divided by total stock handled. |
| **Markdown** | A price reduction to sell near-expiry stock. |
