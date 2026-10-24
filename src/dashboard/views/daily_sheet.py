from __future__ import annotations

from html import escape

import streamlit as st

from dashboard.components import number, show_error


def _list(items: list[dict]) -> str:
    if not items:
        return "<li>None</li>"
    return "".join(
        f"<li><strong>{escape(str(item['name']))}</strong> · {escape(str(item['detail']))}</li>"
        for item in items
    )


def render(client, actor):
    try:
        sheet = client.daily_sheet()
    except Exception as exc:
        show_error(exc)
        return
    groups = (
        ("Bake plan", [{"name": row["product_name"], "detail": f"{number(row['total_quantity'], 0)} units"} for row in sheet.get("bake_plan", [])]),
        ("Use first / expiry", [{"name": row["name"], "detail": f"{row['quantity']} · {row['bucket']} · expires {row['expiry_date']}"} for row in sheet.get("expiry_tasks", [])]),
        ("Actions to review", [{"name": row["product_name"], "detail": f"{row['action']} {row['quantity']} · {row['rationale']}"} for row in sheet.get("actions", [])]),
        ("Deliveries", [{"name": f"Order #{row['order_id']}", "detail": f"due {row['expected_date']}"} for row in sheet.get("deliveries", [])]),
    )
    st.markdown('<div class="daily-sheet">', unsafe_allow_html=True)
    st.markdown(f"<h2>Daily sheet · {escape(str(sheet['business_date']))}</h2>", unsafe_allow_html=True)
    st.caption("Floor and bakery handoff · read-only")
    for title, rows in groups:
        st.markdown(f"<h3>{title}</h3><ul>{_list(rows)}</ul>", unsafe_allow_html=True)
    st.caption(sheet["note"])
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("Print / Save PDF", icon=":material/print:", type="primary"):
        st.html("<script>window.parent.print()</script>", unsafe_allow_javascript=True)
