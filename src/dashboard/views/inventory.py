from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import altair as alt
import pandas as pd
import streamlit as st

from dashboard.components import metric_row, number, section_header, show_error


def _receive_form(client, products, actor):
    with st.form("receive-batch"):
        product = st.selectbox(
            "Product", products, format_func=lambda row: f"{row['sku']} · {row['name']}"
        )
        code = st.text_input("Batch code", value=f"UI-{uuid4().hex[:8].upper()}")
        quantity = st.number_input("Quantity received", min_value=0.001, value=10.0, step=1.0)
        today = date.fromisoformat(st.session_state.business_date)
        received = st.date_input("Received date", value=today)
        expiry = st.date_input("Expiry date", value=today + timedelta(days=2))
        cost = st.number_input("Unit cost", min_value=0.0, value=2.5, step=0.1)
        if st.form_submit_button("Receive stock", type="primary", icon=":material/add:"):
            try:
                client.receive_batch(
                    {
                        "product_id": product["id"],
                        "batch_code": code,
                        "quantity_received": str(quantity),
                        "received_date": received.isoformat(),
                        "expiry_date": expiry.isoformat(),
                        "unit_cost": str(cost),
                        "request_id": f"ui-receipt-{uuid4().hex[:10]}",
                        **actor,
                    }
                )
                st.success("Batch received")
                st.rerun()
            except Exception as exc:
                show_error(exc)


def _adjust_form(client, batches, products, actor):
    with st.form("adjust-batch"):
        batch = st.selectbox(
            "Batch",
            batches,
            format_func=lambda row: (
                f"#{row['id']} · {row['batch_code']} · "
                f"{number(row['quantity_remaining'], 2)} left"
            ),
        )
        delta = st.number_input("Adjustment (+/-)", value=-1.0, step=1.0)
        if st.form_submit_button(
            "Record adjustment", type="primary", icon=":material/edit:"
        ):
            try:
                client.adjustment(
                    {
                        "product_id": batch["product_id"],
                        "batch_id": batch["id"],
                        "quantity_delta": str(delta),
                        "request_id": f"ui-adjust-{uuid4().hex[:10]}",
                        **actor,
                    }
                )
                st.success("Adjustment recorded")
                st.rerun()
            except Exception as exc:
                show_error(exc)


def render(client, actor):
    try:
        positions = client.positions()
        products = client.products()
        batches = client.batches()
    except Exception as exc:
        show_error(exc)
        return
    product_names = {row["id"]: row["name"] for row in products}
    batch_codes = {row["id"]: row["batch_code"] for row in batches}

    metric_row(
        [
            ("Products", str(len(products)), None, "basket", ""),
            ("Open batches", str(len(batches)), None, "croissant", "amber"),
            (
                "Saleable units",
                number(sum(float(row["saleable_on_hand"]) for row in positions), 0),
                None,
                "loaf",
                "sage",
            ),
            (
                "On order",
                number(sum(float(row["on_order"]) for row in positions), 0),
                "Approved and not overdue",
                "receipt",
                "eucalyptus",
            ),
        ]
    )

    section_header(
        "Stock position",
        "Saleable stock excludes expired and quarantined batches",
        "scale",
    )
    chart_data = pd.DataFrame(
        [
            {
                "Product": row["name"],
                "Saleable": float(row["saleable_on_hand"]),
                "Physical": float(row["physical_on_hand"]),
            }
            for row in positions
        ]
    )
    if not chart_data.empty:
        long_data = chart_data.melt(
            id_vars="Product",
            value_vars=["Saleable", "Physical"],
            var_name="Measure",
            value_name="Units",
        )
        chart = (
            alt.Chart(long_data)
            .mark_bar(cornerRadius=4)
            .encode(
                x=alt.X("Product:N", axis=alt.Axis(labelAngle=0, title=None)),
                xOffset=alt.XOffset("Measure:N", sort=["Saleable", "Physical"]),
                y=alt.Y("Units:Q", axis=alt.Axis(title=None, grid=False)),
                color=alt.Color(
                    "Measure:N",
                    scale=alt.Scale(
                        domain=["Saleable", "Physical"],
                        range=["#A8431F", "#E39A2D"],
                    ),
                    legend=alt.Legend(orient="top", title=None),
                ),
                tooltip=["Product", "Measure", "Units"],
            )
            .properties(height=220)
            .configure_view(strokeOpacity=0)
            .configure_axis(
                labelColor="#7B6A58",
                domainColor="#E8DAC5",
                tickColor="#E8DAC5",
                grid=False,
            )
            .configure_legend(labelColor="#3B2A1E")
        )
        st.altair_chart(chart, width="stretch")

    st.dataframe(
        [
            {
                "SKU": row["sku"],
                "Product": row["name"],
                "Saleable": row["saleable_on_hand"],
                "Physical": row["physical_on_hand"],
                "Expired": row["expired_quantity"],
                "On order": row["on_order"],
                "Shelf life": row["remaining_shelf_life_days"],
                "Risk": row["risk_score"],
            }
            for row in positions
        ],
        hide_index=True,
        width="stretch",
    )

    tab_batches, tab_receive, tab_adjust, tab_ledger = st.tabs(
        ["Batches", "Receive", "Adjust", "Ledger"]
    )
    with tab_batches:
        st.dataframe(
            [
                {
                    "Batch": row["batch_code"],
                    "Product": str(product_names.get(row["product_id"], row["product_id"] or "—")),
                    "Remaining": row["quantity_remaining"],
                    "Expiry": row["expiry_date"],
                    "Status": row["status"],
                }
                for row in batches
            ],
            hide_index=True,
            width="stretch",
        )
    with tab_receive:
        _receive_form(client, products, actor)
    with tab_adjust:
        _adjust_form(client, batches, products, actor)
    with tab_ledger:
        try:
            movements = client.movements()
            st.dataframe(
                [
                    {
                        "Time": row["occurred_at"],
                        "Product": str(product_names.get(row["product_id"], row["product_id"] or "—")),
                        "Batch": str(batch_codes.get(row["batch_id"], row["batch_id"] or "—")),
                        "Type": row["movement_type"],
                        "Delta": row["quantity_delta"],
                        "Reason": row["reason"],
                    }
                    for row in movements
                ],
                hide_index=True,
                width="stretch",
            )
        except Exception as exc:
            show_error(exc)
