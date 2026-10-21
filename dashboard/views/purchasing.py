from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import streamlit as st

from dashboard.components import empty_state, metric_row, section_header, show_error


def _create_form(client, suppliers, products, actor):
    with st.form("create-po"):
        supplier = st.selectbox("Supplier", suppliers, format_func=lambda row: row["name"])
        product = st.selectbox(
            "Product", products, format_func=lambda row: f"{row['sku']} · {row['name']}"
        )
        quantity = st.number_input("Quantity", min_value=0.001, value=20.0, step=1.0)
        cost = st.number_input("Unit cost", min_value=0.0, value=2.5, step=0.1)
        today = date.fromisoformat(st.session_state.business_date)
        expected = st.date_input("Expected date", value=today + timedelta(days=2))
        if st.form_submit_button(
            "Create draft purchase order", type="primary", icon=":material/add:"
        ):
            try:
                client.create_purchase_order(
                    {
                        "supplier_id": supplier["id"],
                        "expected_date": expected.isoformat(),
                        "lines": [
                            {
                                "product_id": product["id"],
                                "quantity": str(quantity),
                                "unit_cost": str(cost),
                            }
                        ],
                    }
                )
                st.success("Draft purchase order created")
                st.rerun()
            except Exception as exc:
                show_error(exc)


def _receive_form(client, order, products, actor):
    names = {row["id"]: row["name"] for row in products}
    line = st.selectbox(
        "Line",
        order["lines"],
        format_func=lambda row: (
            f"{names.get(row['product_id'], row['product_id'])} · {row['quantity']} ordered · "
            f"{row['received_quantity']} received"
        ),
        key=f"line-{order['id']}",
    )
    outstanding = float(line["quantity"]) - float(line["received_quantity"])
    quantity = st.number_input(
        "Receiving now",
        min_value=0.001,
        max_value=max(0.001, outstanding),
        value=max(0.001, outstanding),
        key=f"receive-qty-{order['id']}",
    )
    today = date.fromisoformat(st.session_state.business_date)
    received = st.date_input("Received date", value=today, key=f"received-{order['id']}")
    expiry = st.date_input(
        "Expiry date", value=today + timedelta(days=3), key=f"expiry-{order['id']}"
    )
    if st.form_submit_button(
        "Receive line", type="primary", key=f"receive-{order['id']}", icon=":material/download:"
    ):
        try:
            client.receive_purchase_order(
                order["id"],
                {
                    "request_id": f"ui-po-{uuid4().hex[:10]}",
                    "lines": [
                        {
                            "purchase_order_line_id": line["id"],
                            "quantity": str(quantity),
                            "received_date": received.isoformat(),
                            "expiry_date": expiry.isoformat(),
                        }
                    ],
                    **actor,
                },
            )
            st.success("Delivery recorded")
            st.rerun()
        except Exception as exc:
            show_error(exc)


def render(client, actor):
    try:
        orders = client.purchase_orders()
        suppliers = client.suppliers()
        products = client.products()
    except Exception as exc:
        show_error(exc)
        return
    metric_row(
        [
            ("Suppliers", str(len(suppliers)), None, "basket", ""),
            ("Orders", str(len(orders)), None, "receipt", "amber"),
            (
                "Approved",
                str(sum(1 for order in orders if order["status"] == "APPROVED")),
                None,
                "check",
                "sage",
            ),
            (
                "Received",
                str(sum(1 for order in orders if order["status"] == "RECEIVED")),
                None,
                "loaf",
                "eucalyptus",
            ),
        ]
    )
    with st.expander("New purchase order", expanded=False):
        _create_form(client, suppliers, products, actor)

    section_header("Orders", "Draft → approved → received", "receipt")
    if not orders:
        empty_state(
            "The basket is empty",
            "No purchase orders yet. Create a draft to plan the next delivery.",
            "basket",
        )
    names = {row["id"]: row["name"] for row in products}
    for order in orders:
        with st.expander(
            f"#{order['id']} · {order['status']} · expected {order['expected_date']}"
        ):
            st.dataframe(
                [
                    {
                        "Line": line["id"],
                        "Product": names.get(line["product_id"], line["product_id"]),
                        "Ordered": line["quantity"],
                        "Received": line["received_quantity"],
                        "Unit cost": line["unit_cost"],
                    }
                    for line in order["lines"]
                ],
                hide_index=True,
                width="stretch",
            )
            if order["status"] == "DRAFT":
                if st.button(
                    "Approve order",
                    key=f"approve-po-{order['id']}",
                    type="primary",
                    icon=":material/check_circle:",
                ):
                    try:
                        client.approve_purchase_order(order["id"], actor)
                        st.rerun()
                    except Exception as exc:
                        show_error(exc)
            if order["status"] == "APPROVED":
                with st.form(f"receive-po-{order['id']}"):
                    _receive_form(client, order, products, actor)
