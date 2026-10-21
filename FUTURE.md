# FUTURE.md — From Scaffold to Demo-Winning Product

This document turns the requirements in `README.md` into a practical roadmap of
high-impact, feasible features. It separates work that finishes the promised MVP from the
"cool factor" that makes the product memorable in a demo.

The guiding idea:

> Do not build another dashboard with a chatbot bolted on.
> Build a trustworthy time machine for a small food shop: see the risk, understand the
> recommendation, approve it, then watch waste fall.

---

## 1. Where the project is today

The README describes the full system. The repository has two working islands:

| Part | Current state |
|---|---|
| `backend/` | Working FastAPI + SQLAlchemy + SQLite foundation. Suppliers, products, batches, receipts, purchase orders, movements, activity log, CSV export, tests. |
| `forecast/` | Working standalone forecast and reorder engine. Baseline forecast, policies, recommendations, metrics, optional ML challenger. |
| Dashboard | Not implemented. |
| FEFO sales/waste/donation | Not implemented. `POST /stock-actions` returns 501. |
| Recommendations through the API | Not implemented. Endpoint returns 501. |
| SDG reporting | Not implemented. Seed factors are zero-valued placeholders. |
| Bakery planning | Tables exist; business logic is not connected. |

The biggest gap is not intelligence. It is **integration and visibility**.

Three things must happen before advanced features matter:

1. The backend must actually allocate stock with FEFO.
2. The forecast package must be connected to backend products, batches, and movements.
3. A dashboard must make the loop visible: expiry → recommendation → approval → outcome.

Everything below is ordered with that in mind.

---

## 2. What "cool" means for this project

Winning food-waste and AI projects usually share one or more of these traits:

- **A visible end-to-end loop**, not isolated model output.
- **A memorable demo moment**, such as selling the oldest batch or simulating a week.
- **Human control**, especially for money, discounts, donations, and production.
- **Explainable recommendations**, so a judge can see why the system said "bake 118".
- **Measurable impact**, expressed in waste, cost, meals, or CO2e with clear assumptions.
- **Deterministic demos**, so the story works every time.

For this project, the strongest differentiator is the combination of:

```text
FEFO ledger
   + explainable forecast
   + human approval
   + scenario simulation
   + estimated waste/SDG impact
```

That is more defensible than claiming a slightly better ML model on synthetic data.

---

## 3. Lessons from previous hackathon winners

These projects are useful as pattern references, not as features to copy wholesale.

| Project | What it did well | What to borrow here | What not to copy |
|---|---|---|---|
| **Hack4Food 2025 winner** | Predicted daily food demand, analysed unsold food, suggested reuse or donation. | Demand-driven recommendations plus rescue actions. | Computer vision and RAG suggestions that need extra infrastructure. |
| **EdgeCart, HackPrinceton 2025** | Detected freshness, applied dynamic discounts, and used donation as a zero-waste fallback. | Expiry-aware markdown urgency and a donation path. | Camera-based freshness detection and customer targeting. |
| **MyFridge, McHacks 12** | Receipt scanning, expiry tracking, and recipe suggestions. | Expiry-first UX and "use it before it spoils" guidance. | OCR as a hard dependency unless a real library is added. |
| **EcoChef / Savour, food-waste hackathons** | Connected near-expiry food with demand and surfaced impact. | Rescue mode and a simple consumer-friendly story. | A public marketplace, which is outside this single-shop scope. |
| **AgentOps Flight Deck** | Turned agent decisions into approval queues, trace views, and a judge mode. | Approval inbox, audit timeline, deterministic demo mode. | Agent orchestration complexity that does not serve the shop workflow. |
| **HaLoop** | Made human-in-the-loop governance the headline feature. | Explainable decisions, role boundaries, and override records. | Full RBAC or production security claims for a prototype. |
| **PROMETHEUS** | Ran challenger reasoning and ended with an explicit decision gate. | Baseline vs ML comparison and a visible promotion gate. | Multi-agent adversarial theatre that distracts from the shop problem. |
| **Waste Watcher AI, Cornell 2024** | Made waste measurement the core story. | Waste analytics and a before/after narrative. | Plate-return cameras and hardware. |

Common winner pattern:

```text
Real problem → visible workflow → explainable decision → human approval → measurable outcome
```

---

## 4. Feature catalogue

Effort estimates assume this repository and a small team:

- **S** — under a day.
- **M** — one to two focused days.
- **L** — three or more focused days, or meaningful new infrastructure.

Feasibility assumes Python, FastAPI, SQLite, Streamlit, and the existing forecast package.

### A. Trust and control — the strongest differentiator

| Feature | Wow moment | README requirement | Effort | Feasibility |
|---|---|---|---|---|
| **FEFO rescue console** | Sell 5 milk and watch the oldest batches drain first; expired stock is hard-blocked. | FEFO, sales/issues, food safety | M | High |
| **Expiry wall** | Countdown cards for expired, critical, warning, and healthy stock, with value at risk. | Expiry buckets and alerts | S | High |
| **Approval inbox** | Approve, edit, or reject a recommendation with a reason, in one screen. | Human control, approval workflow | M | High |
| **Audit replay** | Scrub a timeline of receipt → sale → recommendation → approval → outcome. | Logged outcome, audit trail | M | High |
| **Explainability card** | Expand any recommendation into its calculation and reason codes. | Written rationale, confidence | S | High |
| **Data-quality badge** | Show "stale data", "low history", "stockout days excluded", or "ML fallback". | Forecast caveats, fallback rules | S | High |
| **Judge mode** | One button resets, reseeds, and runs a scripted scenario. | Demo script, repeatable seed | S | High |

Why it matters: the README already requires human approval for purchases, markdowns,
donations, and bake-plan changes. Making that control visible is both a requirement and a
strong demo feature.

### B. Time machine and simulation — the most visual

| Feature | Wow moment | README requirement | Effort | Feasibility |
|---|---|---|---|---|
| **Week simulator** | Advance seven days; sales consume stock, orders arrive, and waste/stockouts accumulate. | Scenario review, outcome logging | L | High |
| **Scenario lab** | Sliders for demand, supplier delay, service level, and shelf life recompute recommendations instantly. | Forecast and reorder tuning | M | High |
| **Habit vs system comparison** | Run "order from habit" versus "follow recommendations" and show the difference. | Business benefit, waste reduction | M | High |
| **Backtest explorer** | Pick a past date and compare forecast against actual sales. | MAE/MAPE, holdout evaluation | M | High |
| **Holiday/promotion what-if** | Apply a 1.4× Saturday multiplier and watch the bake plan change. | Calendar overrides | S | High |

The week simulator is the single best "cool" feature after FEFO. It converts a static
recommendation into a story with consequences.

### C. Rescue and sustainability — the emotional payoff

| Feature | Wow moment | README requirement | Effort | Feasibility |
|---|---|---|---|---|
| **Rescue mode** | Near-expiry products automatically enter a markdown queue with urgency and deadline. | Markdown suggestions | M | High |
| **Donation routing** | Match safe surplus to a partner and record a donation movement. | Donations, SDG 2.1 | M | High |
| **SDG impact receipt** | After the simulation: waste avoided, CO2e avoided, meals donated, revenue recovered. | SDG 12.3, 12.5, 13.2 | M | High |
| **Waste autopsy** | Classify waste as over-ordering, weak demand, late markdown, or supplier issue. | Waste analytics | M | High |
| **Assumption panel** | Show conversion factors, baseline policy, and "estimate only" labels. | SDG guardrails | S | High |

Important: CO2e, meal equivalents, and SDG contributions must remain explicitly labelled
as estimates with documented assumptions. The existing zero-valued seed factors are not
real measurements.

### D. Forecast intelligence — show judgement, not just a model

| Feature | Wow moment | README requirement | Effort | Feasibility |
|---|---|---|---|---|
| **Champion/challenger panel** | Baseline and ML side by side with WAPE, bias, coverage, and gate result. | ML promotion gate | M | High |
| **Fallback badge** | When ML cannot serve, show why and display the baseline result. | ML-to-baseline fallback | S | High |
| **Rolling-origin backtest** | Prove the forecast across many past dates, not one holdout. | Backtesting | M | High |
| **Cold-start assistant** | A new product gets a category-based start and a low-confidence label. | New-product fallback | S | High |
| **Stockout-censoring visual** | Show which zero-sale days were excluded and why. | Censored demand guardrail | S | High |

The repo already implements most of this logic. The missing piece is making it legible to a
non-technical judge.

### E. Bakery depth — the domain-specific wow

| Feature | Wow moment | README requirement | Effort | Feasibility |
|---|---|---|---|---|
| **Bake plan by daypart** | Morning, midday, afternoon, and evening quantities with oven-capacity checks. | Bakery daily bake plan | L | High |
| **Weekday demand factors** | Saturday and Monday behaviour learned from history. | Weekday forecasting | M | High |
| **Seasonal ingredient calendar** | Highlight in-season, local, and price-friendly ingredients. | Seasonal ingredient advice | M | High |
| **Seasonal bread advice** | Rule-based suggestions for autumn rye, winter stollen, and similar. | Seasonal recommendations | S | High |
| **Markdown windows** | Discount remaining bread after 17:30, donate before close. | Markdown/donation policy | M | High |
| **Allergen and ingredient gate** | Block a bake plan when an ingredient or allergen constraint fails. | Allergen checks | M | High |

Bakery behaviour must stay behind `DemandPolicy`, `PlanningPolicy`, and `AdvicePolicy`.
Do not add `if bakery` branches to shared services.

### F. Data entry and convenience — useful, but lower wow

| Feature | Wow moment | README requirement | Effort | Feasibility |
|---|---|---|---|---|
| **Receipt import** | Upload a JSON/CSV delivery file and create batches. | Receipts | S | High |
| **Barcode/QR lookup** | Simulated scan opens the batch and its expiry status. | Batch traceability | M | Medium |
| **CSV inventory export** | Download the current batch snapshot from the dashboard. | CSV export | S | High |
| **Role-based views** | Owner, manager, baker, and shop-staff views. | Role-based permissions | M | Medium |
| **Shop-floor view** | Large "use first / buy now / bake plan" cards. | Daily review screen | M | High |

Receipt OCR is possible only if a real OCR dependency is added. It should not block the
core demo.

---

## 5. Feasibility tiers

### Tier 1 — build now, high confidence

These are feasible end-to-end with the current stack:

- FEFO sale, waste, and donation service with idempotency and ledger entries.
- Expiry buckets and risk scoring.
- Recommendation adapter from SQLite to the existing `forecast` package.
- Streamlit dashboard: inventory, expiry wall, recommendations, approval inbox.
- Morning briefing and explainability cards.
- Scenario lab and week simulator.
- SDG impact estimates with documented assumptions.
- Bakery bake plan and seasonal advice.
- Champion/challenger comparison using the existing ML code.
- Tests, seed data, and deterministic judge-mode reset.

### Tier 2 — build with mocks or seeded data

- Supplier reliability and overdue-delivery scenarios.
- Receipt OCR, only if an OCR library is accepted.
- Donation partner matching from a local partner table.
- A deterministic "ask the shop" assistant using intent parsing instead of an LLM.
- Barcode input simulated through the UI.

### Tier 3 — do not build for this MVP

- Live POS/ERP integration.
- Real supplier emails or payments.
- Computer-vision freshness detection or IoT sensors.
- Multi-store support.
- Authentication or production RBAC.
- Certified CO2e or SDG accounting.
- Production-grade ML trained on real data.
- A native mobile app.

These are valid future work, but they add risk without improving the core demo.

---

## 6. Recommended build order

### Phase 0 — close the promised MVP

1. Implement FEFO stock actions with:
   - active, nonexpired, positive batches only,
   - ordering by expiry date, received date, then id,
   - one movement per allocated batch,
   - request-level idempotency,
   - a single transaction for all allocations.

2. Add expiry buckets and value-at-risk calculations.

3. Wire `backend/app/services/recommendations.py` to the `forecast` package.

5. Record recommendation decisions and outcomes in the audit trail.

### Phase 1 — demo multipliers

6. Morning briefing with three short lines per recommendation.
7. Rescue mode: markdown and donation suggestions.
8. Explainability cards and reason-code mapping.
9. Judge mode and deterministic demo reset.

### Phase 2 — the spectacle

10. Week simulator / digital twin.
11. Scenario lab with demand and supplier-delay sliders.
12. SDG impact receipt with before/after comparison.
13. Audit replay timeline.

### Phase 3 — depth

14. Champion/challenger forecast panel.
15. Bakery daypart planner and seasonal advice.
16. Waste autopsy.
17. Rolling-origin backtest view.
18. Receipt import and shop-floor view.

---

## 7. Five-minute demo script

1. **Morning briefing** — "Here is what expires, what to sell first, and what to bake."
2. **Expiry wall** — show critical stock and the value at risk.
3. **Sell 5 milk** — FEFO consumes the oldest batch first; expired stock is rejected.
4. **Explain a recommendation** — show the forecast, safety stock, reorder point, and shelf-life cap.
5. **Scenario lab** — increase Saturday demand by 20%; the bake plan changes from 100 to 118 loaves.
6. **Approve the bake plan** — record the approver and reason in the audit trail.
7. **Advance seven days** — show stock, waste, and stockouts accumulating.
8. **SDG receipt** — show kg waste avoided, estimated CO2e avoided, and meals donated.
9. **Champion/challenger** — show why the ML model was not promoted: WAPE, bias, or coverage failed the gate.

The story ends with a measurable outcome, not a model-accuracy claim.

---

## 8. Guardrails for every future feature

- **Never sell expired stock.** Hard-block it in the service, not only in the UI.
- **Never change stock without a movement.** Corrections are new adjustment movements.
- **Never let an ML forecast bypass the baseline fallback.**
- **Never train on stockout-censored days as if they were true low demand.**
- **Never auto-approve spending, markdowns, donations, or bake changes** in this MVP.
- **Keep bakery behaviour behind policy interfaces.**
- **Label SDG, CO2e, and meal figures as estimates** and show the assumptions.
- **Keep the demo deterministic.** A judge mode should reset to a known state.
- **Do not commit generated databases or artifacts.**

---

## 9. Success measures for the future work

A feature earns its place if it improves at least one of these:

| Measure | Target for the demo |
|---|---|
| Time to first useful recommendation | Under 15 minutes from a clean setup |
| Daily review time | Under 5 minutes |
| Expired sales | Zero |
| Recommendation explainability | Every recommendation has a reason code and plain-language "why" |
| Waste visibility | Waste, markdown, and donation quantities visible by product and cause |
| Forecast honesty | Confidence and fallback state always visible |
| Demo reliability | Judge mode reproduces the same story every run |
| SDG transparency | Assumptions and factors shown next to every estimate |

---

## 10. Explicitly out of scope

The README already defers these. Keep them out of the core build:

- Authentication and real permissions.
- Multi-warehouse support.
- POS/ERP integration.
- Automated supplier emails.
- Payment processing.
- Full recipe/MRP planning.
- Native mobile application.
- Computer vision and IoT hardware.
- Certified sustainability accounting.

---

## 11. References

- Hack4Food 2025 winner — demand prediction and unsold-food reuse:
  [LinkedIn summary](https://www.linkedin.com/posts/rabi3hs_we-won-hack4food-2025-proud-to-share-activity-7322564618998960130-gn_m)
- EdgeCart, HackPrinceton 2025 — freshness-aware discounts and donation fallback:
  [GitHub](https://github.com/AntoDono/edgecart)
- MyFridge, McHacks 12 — receipt scanning, expiry tracking, and recipe suggestions:
  [GitHub](https://github.com/bogdanSgithub/MyFridge)
- EcoChef, GenAI Hackathon for SDGs — near-expiry food and AI recipe matching:
  [HKUST summary](https://ais.hkust.edu.hk/whats-happening/news/tm-ddp-students-won-genai-hackathon-innovative-food-waste-mobile-app-solution)
- Savour, AI for Impact APAC 2024 runner-up — inventory optimization and expiry alerts:
  [Hack2skill summary](https://blog.hack2skill.com/teams-that-emerged-victorious-ai-for-impact-hackathon)
- AgentOps Flight Deck — approval queues, trace views, and judge mode:
  [Project page](https://virtual-events.aitinkerers.org/hackathons/h_lKGKukpDyvw/entries/ht_GJ5MsV60XFA)
- HaLoop — human-in-the-loop governance and explainable review decisions:
  [GitHub](https://github.com/DasbootU9607/Deep-Learning-Week-Hackathon-2026-HaLoop-Team-CEEES)
- PROMETHEUS — challenger reasoning and decision gate:
  [lablab submission](https://lablab.ai/submissions/olh9sjxvqi3k4ktxk8aa6lyl)

These references are inspiration for patterns, not claims that this project matches their
scope or results.
