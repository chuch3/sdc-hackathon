from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.art import icon
from dashboard.components import (
    metric_row,
    note_card,
    number,
    section_header,
    show_error,
)


def _percent(value, places: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.{places}f}%"


def _proof_section(proof: dict) -> None:
    accuracy = proof["accuracy"]
    observed = proof["observed"]
    projection = proof["projection"]
    section_header(
        "Impact proof",
        f"Holdout accuracy for the last {proof['window_days']} days, "
        f"cut off {proof['cutoff']}",
        "check",
    )
    metric_row(
        [
            (
                "Forecast WAPE",
                _percent(accuracy["wape"]),
                "Lower is better · censored days excluded",
                "chart",
                "eucalyptus",
            ),
            (
                "Forecast bias",
                "n/a" if accuracy["bias"] is None else f"{accuracy['bias']:+.2f}",
                "Positive means over-forecasting",
                "scale",
                "amber",
            ),
            (
                "80% coverage",
                _percent(accuracy["coverage_80"]),
                "Actual inside the forecast range",
                "check",
                "sage",
            ),
            (
                "Observations",
                number(accuracy["observations"], 0),
                f"{accuracy['excluded_censored']} censored day(s) excluded",
                "clock",
                "",
            ),
        ]
    )
    left, right = st.columns([1.2, 1])
    with left:
        section_header(
            "Observed",
            f"Recorded in the last {proof['window_days']} days",
            "basket",
        )
        metric_row(
            [
                (
                    "Sales",
                    number(observed["sales_units"], 0),
                    "Units sold",
                    "receipt",
                    "",
                ),
                (
                    "Waste",
                    number(observed["waste_units"], 0),
                    "Units written off",
                    "alert",
                    "berry",
                ),
                (
                    "Donated",
                    number(observed["donation_units"], 0),
                    "Units given safely",
                    "heart",
                    "sage",
                ),
            ]
        )
        st.caption(
            f"{observed['stockout_events']} stockout event(s) · "
            f"{number(observed['estimated_co2e_kg'], 1)} kg CO2e estimated"
        )
    with right:
        section_header("Run-rate", projection["basis"], "chart")
        st.markdown(
            f"""
            <div class="status-grid">
              <div class="status-row"><span>Annualised waste</span>
                <strong>{number(projection['annualised_waste_units'], 0)} units</strong></div>
              <div class="status-row"><span>Annualised donations</span>
                <strong>{number(projection['annualised_donation_units'], 0)} units</strong></div>
              <div class="status-row"><span>Annualised CO2e</span>
                <strong>{number(projection['annualised_estimated_co2e_kg'], 0)} kg</strong></div>
              <div class="status-row"><span>Annualised meals</span>
                <strong>{number(projection['annualised_estimated_meals'], 0)}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            f"Model {proof['model']['forecaster']} · {proof['model']['interval']} "
            "interval · causal attribution needs the switchback test."
        )
    with st.expander("Backtest assumptions", expanded=False):
        for line in proof["assumptions"]:
            st.write(f"- {line}")


def render(client, actor):
    try:
        impact = client.get("analytics/impact", {"days": 30})
        proof = client.proof(14)
    except Exception as exc:
        show_error(exc)
        return
    _proof_section(proof)
    section_header("Latest 30 days", "Estimated waste, donation, and community impact", "leaf")
    metric_row(
        [
            (
                "Waste",
                f"{number(impact['estimated_waste_kg'], 1)} kg",
                "Estimated",
                "alert",
                "berry",
            ),
            (
                "Donated",
                f"{number(impact['estimated_donation_kg'], 1)} kg",
                "Estimated",
                "heart",
                "sage",
            ),
            (
                "Meals",
                number(impact["estimated_meals"], 0),
                "Estimate using configured factors",
                "coffee",
                "amber",
            ),
            (
                "CO2e",
                f"{number(impact['estimated_co2e_kg'], 1)} kg",
                "Estimate using configured factors",
                "leaf",
                "eucalyptus",
            ),
        ]
    )

    left, right = st.columns([1, 1.35])
    with left:
        section_header("Waste vs donation", "Estimated kilograms · 30 days", "chart")
        waste = float(impact["estimated_waste_kg"])
        donated = float(impact["estimated_donation_kg"])
        if waste + donated > 0:
            donut_data = pd.DataFrame(
                [
                    {"Kind": "Waste", "kg": waste},
                    {"Kind": "Donated", "kg": donated},
                ]
            )
            donut = (
                alt.Chart(donut_data)
                .mark_arc(innerRadius=64, outerRadius=96, cornerRadius=6, padAngle=0.03)
                .encode(
                    theta=alt.Theta("kg:Q"),
                    color=alt.Color(
                        "Kind:N",
                        scale=alt.Scale(
                            domain=["Waste", "Donated"],
                            range=["#9B2335", "#6F7F4E"],
                        ),
                        legend=alt.Legend(orient="bottom", title=None),
                    ),
                    tooltip=["Kind", alt.Tooltip("kg:Q", format=".1f")],
                )
                .properties(height=250)
                .configure_view(strokeOpacity=0)
                .configure_legend(labelColor="#3B2A1E")
            )
            st.altair_chart(donut, width="stretch")
        else:
            st.caption("No waste or donation recorded in this window.")
    with right:
        section_header("By product", "Estimated units recorded as waste or donation", "basket")
        st.dataframe(
            [
                {
                    "SKU": row["sku"],
                    "Product": row["name"],
                    "Waste": row["waste"],
                    "Donated": row["donation"],
                    "Unit": row["unit"],
                }
                for row in impact["products"]
            ],
            hide_index=True,
            width="stretch",
        )

    note_card(
        impact["assumption"],
        icon_name="leaf",
        title="How we estimate:",
    )
    factors = impact.get("factors") or []
    if factors:
        st.dataframe(
            [
                {
                    "Category": factor["category"],
                    "kg CO2e per kg wasted": factor["kg_co2e_per_kg_waste"],
                    "Meals per kg donated": factor["meals_per_kg_donated"],
                }
                for factor in factors
            ],
            hide_index=True,
            width="stretch",
        )
        note_card(
            "Factors are illustrative placeholders from published food-category "
            "life-cycle studies, not certified measurements. Replace them with measured "
            "local values before quoting any figure.",
            icon_name="alert",
            tone="amber",
            title="Factor provenance:",
        )
    st.markdown(
        f'<div class="sdg-row">'
        f'<span class="sdg-chip">{icon("leaf", 14)} SDG 12.3 · Waste prevention</span>'
        f'<span class="sdg-chip">{icon("heart", 14)} SDG 2.1 · Safe surplus donation</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
