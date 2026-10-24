from __future__ import annotations

from uuid import uuid4

import streamlit as st

from dashboard.components import (
    freshness_ladder,
    metric_row,
    number,
    section_header,
    show_error,
)


def _action_form(client, items, actor):
    if not items:
        return
    with st.form("expiry-action"):
        item = st.selectbox(
            "Batch",
            items,
            format_func=lambda row: (
                f"{row['sku']} · {row['batch_code']} · "
                f"{row['bucket']} · {number(row['quantity'], 2)}"
            ),
        )
        actions = item["allowed_actions"] or ["WASTE"]
        movement = st.selectbox("Action", actions)
        quantity = st.number_input(
            "Quantity",
            min_value=0.001,
            max_value=float(item["quantity"]),
            value=float(item["quantity"]),
        )
        if st.form_submit_button(
            "Record action", type="primary", icon=":material/check_circle:"
        ):
            try:
                client.stock_action(
                    {
                        "product_id": item["product_id"],
                        "quantity": str(quantity),
                        "movement_type": movement,
                        "request_id": f"ui-{movement.lower()}-{uuid4().hex[:10]}",
                        **actor,
                    }
                )
                st.success(f"{movement.title()} recorded")
                st.rerun()
            except Exception as exc:
                show_error(exc)


def render(client, actor):
    try:
        buckets = client.expiry_buckets()
        alerts = client.expiry_alerts(7)["alerts"]
    except Exception as exc:
        show_error(exc)
        return

    totals = buckets["totals"]
    metric_row(
        [
            ("Expired", number(totals["expired"], 0), "Blocked from sale", "alert", "berry"),
            (
                "Critical",
                number(totals["critical"], 0),
                "Inside the category threshold",
                "flame",
                "berry",
            ),
            (
                "Warning",
                number(totals["warning"], 0),
                "Approaching the threshold",
                "clock",
                "amber",
            ),
            (
                "Value at risk",
                f"${number(buckets['value_at_risk'], 2)}",
                "Estimate",
                "chart",
                "eucalyptus",
            ),
        ]
    )

    freshness_ladder(totals, "Shelf-life runway")

    section_header(
        "Batches to review",
        "Oldest safe stock first; expired stock is blocked",
        "clock",
    )
    st.dataframe(
        [
            {
                "Risk": row["bucket"],
                "SKU": row["sku"],
                "Product": row["name"],
                "Batch": row["batch_code"],
                "Quantity": row["quantity"],
                "Expiry": row["expiry_date"],
                "Days": row["days_to_expiry"],
                "Value": row["value"],
                "Actions": ", ".join(row["allowed_actions"]),
            }
            for row in alerts
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "Days": st.column_config.ProgressColumn(
                "Days", min_value=-1, max_value=7, format="%d"
            ),
            "Value": st.column_config.NumberColumn("Value", format="$%.2f"),
        },
    )

    section_header(
        "Recommended safe action",
        "Every action is recorded in the ledger",
        "leaf",
    )
    _action_form(client, alerts, actor)
    st.caption("Expired stock can only be written off. Donations must be safe and unexpired.")
