from __future__ import annotations

import streamlit as st

from dashboard.components import section_header, show_error
from dashboard.views.today import _card


def render(client, actor):
    try:
        products = {row["id"]: row for row in client.products()}
        data = client.recommendations()
    except Exception as exc:
        show_error(exc)
        return
    recommendations = data["recommendations"]
    actions = sorted({item["action"] for item in recommendations})
    selected = st.multiselect("Action", actions, default=actions)
    filtered = [item for item in recommendations if item["action"] in selected]
    section_header(
        "Review queue",
        f"{len(filtered)} recommendations · engine {data['engine']} · as of {data['as_of']}",
        "sparkle",
    )
    for rec in filtered:
        product = products.get(rec["product_id"])
        if product:
            _card(client, product, rec, actor)
