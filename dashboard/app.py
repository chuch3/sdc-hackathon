from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.api_client import ApiClient, ApiError
from dashboard.art import NAV_ICONS, brand_mark
from dashboard.ascii_magic import ASCII_MAGIC_HTML
from dashboard.components import page_header, pill
from dashboard.views import (
    bakery,
    expiry,
    impact,
    inventory,
    purchasing,
    recommendations,
    settings,
    today,
    week,
)

st.set_page_config(
    page_title="Buns At Work!",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <link rel="preload" href="/app/static/fraunces.woff2" as="font" type="font/woff2" crossorigin>
    <link rel="preload" href="/app/static/nunito-sans.woff2" as="font" type="font/woff2" crossorigin>
    <link rel="stylesheet" href="/app/static/theme.css">
    """,
    unsafe_allow_html=True,
)

st.html(ASCII_MAGIC_HTML, unsafe_allow_javascript=True)

if "fs_dark" not in st.session_state:
    st.session_state.fs_dark = False
st.html(
    "<script>document.documentElement.setAttribute("
    f"'data-fs-theme', '{'dark' if st.session_state.fs_dark else 'light'}');</script>",
    unsafe_allow_javascript=True,
)

params = st.query_params
orbyte_actor = params.get("actor") or params.get("email")
if "actor_name" not in st.session_state:
    st.session_state.actor_name = orbyte_actor or "Demo Owner"
if "actor_role" not in st.session_state:
    st.session_state.actor_role = params.get("role", "owner")
if "reason" not in st.session_state:
    st.session_state.reason = params.get("reason", "Dashboard decision")

NAV_ITEMS = [
    "Today",
    "Week",
    "Inventory",
    "Expiry",
    "Recommendations",
    "Purchasing",
    "Bakery",
    "Impact",
    "Settings",
]
NAV_LABELS = {
    "Today": "Today",
    "Week": "Week board",
    "Inventory": "Inventory",
    "Expiry": "Expiry",
    "Recommendations": "Actions",
    "Purchasing": "Purchasing",
    "Bakery": "Bakery",
    "Impact": "Impact",
    "Settings": "Settings",
}
if "page" not in st.session_state:
    requested = params.get("page")
    st.session_state.page = requested if requested in NAV_ITEMS else "Today"

with st.container(key="top-bar"):
    bar_left, bar_right = st.columns([5.2, 4.8], vertical_alignment="center", wrap=True)
    with bar_left:
        st.markdown(
            '<div class="topbar-note">Autumn bakehouse theme · human approval '
            "required · estimated impact is labelled</div>",
            unsafe_allow_html=True,
        )

    with bar_right:
        logo_col, status_col, controls_col = st.columns(
            [1.9, 1.9, 1.3], vertical_alignment="center", gap="small"
        )
        with logo_col:
            st.markdown(
                f"""
                <div class="topbar-brand brand-right">
                  <div class="brand-mark">{brand_mark()}</div>
                  <div>
                    <div class="brand-name">Buns At Work!</div>
                    <div class="brand-sub">FreshStock Bakehouse</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with controls_col:
            with st.popover("Setup", icon=":material/tune:", width="content"):
                base = st.text_input(
                    "API endpoint",
                    value=st.session_state.get(
                        "api_base", os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1")
                    ),
                )
                st.session_state.api_base = base
                st.caption("Acting as")
                st.session_state.actor_name = st.text_input(
                    "Name", value=st.session_state.actor_name, label_visibility="collapsed"
                )
                roles = ["owner", "manager", "bookkeeper", "baker", "staff", "viewer"]
                index = (
                    roles.index(st.session_state.actor_role)
                    if st.session_state.actor_role in roles
                    else 0
                )
                st.session_state.actor_role = st.selectbox(
                    "Role", roles, index=index, label_visibility="collapsed"
                )
                st.session_state.reason = st.text_input(
                    "Decision note",
                    value=st.session_state.reason,
                    label_visibility="collapsed",
                )
                if params.get("from") == "orbyteApp":
                    st.markdown(pill("Orbyte webview", "blue"), unsafe_allow_html=True)
                st.caption("Every change is written to the shared ledger.")

        client = ApiClient(base)
        try:
            health = client.health()
            st.session_state.business_date = health["business_date"]
            with status_col:
                st.markdown(
                    f'<div class="topbar-status">{pill("API connected", "green")} '
                    f'{pill(health["business_date"], "slate")}</div>',
                    unsafe_allow_html=True,
                )
        except ApiError as exc:
            with status_col:
                st.error(exc.detail)
            st.stop()

with st.container(horizontal=True, key="top-nav", gap="small", vertical_alignment="center", wrap=True):
    for item in NAV_ITEMS:
        if st.button(
            NAV_LABELS[item],
            key=f"nav-{item}",
            icon=NAV_ICONS[item],
            type="primary" if st.session_state.page == item else "secondary",
            help=item,
        ):
            st.session_state.page = item
            st.rerun()
    if st.button(
        "Light mode" if st.session_state.fs_dark else "Dark mode",
        key="theme-toggle",
        icon=":material/light_mode:" if st.session_state.fs_dark else ":material/dark_mode:",
        type="secondary",
        help="Switch the workspace between the paper and the night theme.",
    ):
        st.session_state.fs_dark = not st.session_state.fs_dark
        st.rerun()
page = st.session_state.page

actor = {
    "actor_name": st.session_state.actor_name,
    "actor_role": st.session_state.actor_role,
    "reason": st.session_state.reason,
}

PAGE_COPY = {
    "Today": ("Today's brief", "What needs attention before the next service.", "sun"),
    "Week": (
        "Weekly quest board",
        "Seven projected days of actions, arrivals, and risk.",
        "wheat",
    ),
    "Inventory": ("Stock on hand", "Batches, adjustments, and the movement ledger.", "loaf"),
    "Expiry": (
        "Expiry watch",
        "Use the oldest safe stock first and act before value is lost.",
        "clock",
    ),
    "Recommendations": (
        "Recommended actions",
        "Demand-based decisions with a human approval step.",
        "sparkle",
    ),
    "Purchasing": (
        "Purchase orders",
        "Approve orders and receive deliveries into batches.",
        "basket",
    ),
    "Bakery": (
        "Bake plan",
        "Daypart production, seasonal ingredients, and oven limits.",
        "oven",
    ),
    "Impact": (
        "Waste and community impact",
        "Estimated outcomes, shown with their assumptions.",
        "leaf",
    ),
    "Settings": (
        "Workspace settings",
        "API connection, role simulation, and integration status.",
        "gear",
    ),
}
title, subtitle, page_icon = PAGE_COPY[page]
page_header(title, subtitle, st.session_state.business_date, actor, page_icon)

if page == "Today":
    today.render(client, actor)
elif page == "Week":
    week.render(client, actor)
elif page == "Inventory":
    inventory.render(client, actor)
elif page == "Expiry":
    expiry.render(client, actor)
elif page == "Recommendations":
    recommendations.render(client, actor)
elif page == "Purchasing":
    purchasing.render(client, actor)
elif page == "Bakery":
    bakery.render(client, actor)
elif page == "Impact":
    impact.render(client, actor)
else:
    settings.render(client, actor)
