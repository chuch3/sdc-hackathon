# README Additions — Perishable Food Inventory System

## In one minute

This is a daily food-waste and stock helper for a small bakery or food shop. It watches expiry dates, estimates what will sell, and recommends what to sell first, discount, donate, buy, or bake.

A person approves every action that costs money or affects customers. Every decision is logged so the shop can learn from it and show what happened.

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
