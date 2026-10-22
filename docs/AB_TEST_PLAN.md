# A/B plan: proving the recommendation loop

FreshStock can show a forecast backtest and an observed waste run-rate. Neither proves
that the recommendations *caused* less waste. This plan does.

## Design

Use an interrupted time-series switchback, not a customer-level A/B test:

- **Unit:** store-week.
- **Randomisation:** each week, each participating store is assigned to **Advice on** or
  **Advice off** using `settings.ab_test_seed`. Balance assignments across stores with a
  pre-generated block schedule.
- **Baseline:** 4 weeks before the test, all stores use Advice off.
- **Test:** 8 weeks, alternating assignments. A store must stay in its assigned arm for the
  whole week.
- **One store first:** a single-store pilot is directional only; it cannot give statistical
  confidence. Use 4–8 stores for a decision.

A store-week is the right unit because the intervention is the daily recommendation
workflow. Individual baskets would be contaminated by shop-level stock, staffing, and
promotions.

## Metrics

Primary:

- **Waste cost as a share of sales** (`waste_cost / net_sales`), lower is better.
- **Waste units as a share of units received**, lower is better.

Secondary:

- Lost-sales proxy: rejected stock actions plus recorded `StockoutEvent` rows.
- Markdown sell-through and donation units.
- Recommendation approval rate and edited-quantity rate.
- Stockout rate by week and product category.

Guardrails (must not get materially worse):

- Gross margin and net sales.
- Stockout count and forecast WAPE.
- Food-safety incidents, expired sales attempts, or manual overrides without a reason.
- Staff time: minutes to complete the daily review.

## Analysis

1. Aggregate by store-week. Never treat individual movements as independent samples.
2. Fit a pre-specified model: outcome ~ arm + store + week + baseline outcome. Report the
   arm effect with a **bootstrap 95% confidence interval**, resampling stores (cluster
   bootstrap) and preserving the store-week structure.
3. Check the parallel pre-trend over the 4-week baseline. If trends differ, stop and fix
   the assignment or data before interpreting the test.
4. Report absolute and relative effects, the number of store-weeks, and all guardrails.
5. Do not peek repeatedly and stop on a favourable week. Fix the test length in advance.

With few stores, report the interval and call the result directional. A single store can
show whether the workflow is usable, not whether it reduces waste.

## Decision rule

Promote the default Advice on experience only if:

- primary waste ratio improves, with the 95% interval excluding no improvement, **or**
  the pilot shows a consistent direction and the guardrails are clean while a larger test is
  funded;
- no guardrail breaches its pre-agreed tolerance;
- forecast calibration stays within the existing promotion gate;
- store staff complete the daily review without extra support.

If the effect is flat or uncertain, keep Advice off by default and run a larger switchback.

## Operations

- Pre-register the arm schedule, primary metric, exclusions, and test dates.
- Exclude weeks with closures, stocktake, or unrecorded POS outages; log every exclusion.
- Keep POS ingestion and stock movements unchanged between arms. Only the recommendation
  visibility changes.
- Store the arm in the analytics warehouse, not in a mutable spreadsheet.
- Freeze the model version for the test unless a safety fix is required.

## Known limits

- Seasonality can confound a short test; the switchback and 8-week window reduce but do not
  eliminate it.
- Waste is recorded manually in some shops; audits are required.
- The observed annual run-rate in the Impact screen is a scale reference, not a causal
  claim.
- One store cannot support a statistical promotion decision.
