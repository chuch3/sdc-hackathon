from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.components import (
    metric_row,
    number,
    product_line,
    section_header,
    show_error,
)


def render(client, actor):
    try:
        plan_date = st.date_input(
            "Bake date", value=date.fromisoformat(st.session_state.business_date)
        )
        plans = client.bake_plan(plan_date.isoformat())
        profiles = client.bakery_profiles()
        advice = client.seasonal_advice()
    except Exception as exc:
        show_error(exc)
        return

    metric_row(
        [
            ("Bakery products", str(len(plans)), None, "croissant", ""),
            (
                "Planned units",
                number(sum(float(plan["total_quantity"]) for plan in plans), 0),
                None,
                "loaf",
                "amber",
            ),
            (
                "Seasonal ingredients",
                str(len(advice)),
                "Available this month",
                "pumpkin",
                "sage",
            ),
            ("Profiles", str(len(profiles)), None, "oven", "eucalyptus"),
        ]
    )

    chart_rows = [
        {
            "Product": plan["product_name"],
            "Daypart": slot["daypart"].title(),
            "Quantity": float(slot["quantity"]),
        }
        for plan in plans
        for slot in plan["slots"]
    ]
    if chart_rows:
        chart_data = pd.DataFrame(chart_rows)
        chart = (
            alt.Chart(chart_data)
            .mark_bar(cornerRadius=4)
            .encode(
                x=alt.X(
                    "Daypart:N",
                    sort=["Morning", "Midday", "Afternoon"],
                    axis=alt.Axis(labelAngle=0, title=None),
                ),
                xOffset=alt.XOffset("Product:N"),
                y=alt.Y("Quantity:Q", axis=alt.Axis(title=None, grid=False)),
                color=alt.Color(
                    "Product:N",
                    scale=alt.Scale(range=["#A8431F", "#E39A2D", "#6F7F4E", "#C9622A"]),
                    legend=alt.Legend(orient="top", title=None),
                ),
                tooltip=["Product", "Daypart", "Quantity"],
            )
            .properties(height=230)
            .configure_view(strokeOpacity=0)
            .configure_axis(
                labelColor="#7B6A58",
                domainColor="#E8DAC5",
                tickColor="#E8DAC5",
                grid=False,
            )
            .configure_legend(labelColor="#3B2A1E")
        )
        chart = chart.configure(mark=alt.MarkConfig(tooltip=False))
        st.altair_chart(chart, width="stretch")

    section_header(
        "Bake plan",
        "Drafts need manager approval before production",
        "oven",
    )
    for plan in plans:
        with st.container(border=True):
            st.markdown(
                product_line(
                    plan["product_name"],
                    f"{number(plan['total_quantity'], 0)} units · {plan['reason']}",
                    "bakery",
                ),
                unsafe_allow_html=True,
            )
            st.dataframe(
                [
                    {"Daypart": slot["daypart"], "Quantity": slot["quantity"]}
                    for slot in plan["slots"]
                ],
                hide_index=True,
                width="stretch",
            )
            save, approve = st.columns(2)
            if save.button(
                "Save draft",
                key=f"save-bake-{plan['product_id']}",
                icon=":material/save:",
            ):
                try:
                    client.create_bake_plan(plan_date.isoformat(), plan["product_id"], actor)
                    st.success("Draft saved")
                    st.rerun()
                except Exception as exc:
                    show_error(exc)
            if approve.button(
                "Approve plan",
                key=f"approve-bake-{plan['product_id']}",
                type="primary",
                icon=":material/check_circle:",
            ):
                try:
                    client.create_bake_plan(plan_date.isoformat(), plan["product_id"], actor)
                    client.approve_bake_plan(plan["product_id"], plan_date.isoformat(), actor)
                    st.success("Bake plan approved")
                    st.rerun()
                except Exception as exc:
                    show_error(exc)

    names = {plan["product_id"]: plan["product_name"] for plan in plans}
    left, right = st.columns(2)
    with left:
        section_header("Seasonal advice", "This month", "pumpkin")
        st.dataframe(
            [
                {
                    "Ingredient": row["name"],
                    "Availability": f"{row['availability_score']:.0%}",
                    "Price": row["price_index"],
                    "Local": row["local"],
                }
                for row in advice
            ],
            hide_index=True,
            width="stretch",
        )
    with right:
        section_header("Profiles", "Daily limits and daypart mix", "scale")
        st.dataframe(
            [
                {
                    "Product": names.get(row["product_id"], row["product_id"]),
                    "Max daily": row["max_daily_quantity"],
                    "Dayparts": ", ".join((row["daypart_shares"] or {}).keys()),
                }
                for row in profiles
            ],
            hide_index=True,
            width="stretch",
        )
