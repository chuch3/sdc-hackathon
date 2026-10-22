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


def render(client, actor):
    try:
        impact = client.get("analytics/impact", {"days": 30})
    except Exception as exc:
        show_error(exc)
        return
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
