from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

from dashboard.art import category_icon, icon
from dashboard.components import (
    action_pill,
    confidence,
    freshness_ladder,
    hero,
    metric_row,
    number,
    pill,
    readiness_card,
    risk_pill,
    section_header,
    show_error,
    ticker,
)


def _flash(message: str, tone: str = "success") -> None:
    """Show a message that survives the rerun that follows a decision."""
    st.session_state["flash"] = (tone, message)


def _show_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    tone, message = flash
    if tone == "success":
        st.success(message)
    elif tone == "warning":
        st.warning(message)
    else:
        st.error(message)


def _execute(client, product, rec, actor, decision: str, quantity=None):
    action = rec["action"]
    qty = quantity if quantity is not None else rec["quantity"]
    result = None
    if decision == "APPROVED":
        if action == "BUY" and float(qty) > 0:
            if not product.get("supplier_id"):
                raise RuntimeError("This product has no supplier; add one before ordering")
            order = client.create_purchase_order(
                {
                    "supplier_id": product["supplier_id"],
                    "expected_date": (date.today() + timedelta(days=1)).isoformat(),
                    "lines": [
                        {
                            "product_id": product["id"],
                            "quantity": str(qty),
                            "unit_cost": str(product.get("unit_cost", "0")),
                        }
                    ],
                }
            )
            client.approve_purchase_order(order["id"], actor)
            result = f"Draft purchase order #{order['id']} approved"
        elif action == "BAKE" and float(qty) > 0:
            today = st.session_state.business_date
            client.create_bake_plan(today, product["id"], actor)
            client.approve_bake_plan(product["id"], today, actor)
            result = "Bake plan generated and approved"
        elif action in {"DONATE", "WASTE"} and float(qty) > 0:
            client.stock_action(
                {
                    "product_id": product["id"],
                    "quantity": str(qty),
                    "movement_type": action,
                    "request_id": f"ui-{action.lower()}-{uuid4().hex[:10]}",
                    "actor_name": actor["actor_name"],
                    "actor_role": actor["actor_role"],
                    "reason": actor["reason"],
                }
            )
            result = f"{action.title()} recorded"
    client.decide(
        product["id"],
        {
            **actor,
            "decision": decision,
            "action": action,
            "quantity": rec["quantity"],
            "edited_quantity": None if quantity is None else str(quantity),
            "note": rec.get("rationale", "")[:300],
        },
    )
    return result


DECISION_PILL = {
    "APPROVED": ("Approved", "green"),
    "EDITED": ("Edited", "amber"),
    "REJECTED": ("Rejected", "red"),
}


def _card(client, product, rec, actor):
    decision = rec.get("decision")
    with st.container(border=True):
        left, right = st.columns([3, 1])
        with left:
            meta = (
                f"{number(rec['quantity'], 1)} {product['unit']} · "
                f"{number(rec['confidence'] * 100)}% confidence · "
                f"{rec['forecast_horizon_days']}d horizon"
            )
            decision_html = ""
            if decision:
                label, tone = DECISION_PILL.get(decision, (decision.title(), "slate"))
                decision_html = f' {pill(label, tone)}'
            st.markdown(
                f'<div class="product-line">'
                f'<span class="product-icon">{icon(category_icon(product.get("category")), 18)}</span>'
                f'<div><div class="product-name">{escape(product["name"])} '
                f"{action_pill(rec['action'])} {risk_pill(rec['expiry_risk'])}{decision_html}</div>"
                f'<div class="product-meta">{escape(meta)}</div></div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(confidence(rec["confidence"]), unsafe_allow_html=True)
        with right:
            st.markdown(
                f"<div class='big-number'>{number(rec['quantity'], 0)}</div>",
                unsafe_allow_html=True,
            )
        if decision:
            decided_at = rec.get("decided_at") or ""
            stamp = decided_at[:16].replace("T", " ") if decided_at else ""
            st.markdown(
                f'<div class="decision-note">Recorded as {escape(decision.title())}'
                f"{' by ' + escape(rec.get('decided_by') or '') if rec.get('decided_by') else ''}"
                f"{' · ' + escape(stamp) if stamp else ''}.</div>",
                unsafe_allow_html=True,
            )
        with st.expander("Baker's note", expanded=False):
            for line in rec.get("why", []):
                st.write(f"- {line}")
            st.caption(rec.get("rationale", ""))
            st.caption(
                f"Model: {rec.get('model_name', 'baseline')} · "
                f"Run: {rec.get('forecast_run_id', '')[:8]}"
            )
        approve, reject, edit = st.columns(3)
        if approve.button(
            "Approve",
            key=f"approve-{product['id']}",
            type="primary",
            icon=":material/check_circle:",
        ):
            try:
                message = _execute(client, product, rec, actor, "APPROVED")
                _flash(message or f"{product['name']} approved")
            except Exception as exc:
                _flash(str(exc), "error")
            st.rerun()
        if reject.button("Reject", key=f"reject-{product['id']}", icon=":material/cancel:"):
            try:
                _execute(client, product, rec, actor, "REJECTED")
                _flash(f"{product['name']} rejected", "warning")
            except Exception as exc:
                _flash(str(exc), "error")
            st.rerun()
        if edit.button("Edit", key=f"edit-{product['id']}", icon=":material/edit:"):
            st.session_state[f"edit-{product['id']}"] = True
        if st.session_state.get(f"edit-{product['id']}"):
            with st.form(f"edit-form-{product['id']}"):
                quantity = st.number_input(
                    "New quantity",
                    min_value=0.0,
                    value=float(rec["quantity"]),
                    step=1.0,
                    key=f"qty-{product['id']}",
                )
                if st.form_submit_button(
                    "Save edited decision", type="primary", icon=":material/save:"
                ):
                    try:
                        message = _execute(
                            client, product, rec, actor, "EDITED", quantity=quantity
                        )
                        _flash(message or f"{product['name']} edited")
                        st.session_state.pop(f"edit-{product['id']}", None)
                    except Exception as exc:
                        _flash(str(exc), "error")
                    st.rerun()


def render(client, actor):
    _live_body(client, actor)


def _live_strip(version: int, timezone_name: str) -> None:
    stamp = datetime.now(ZoneInfo(timezone_name)).strftime("%H:%M:%S")
    st.markdown(
        f"""
        <div class="live-strip">
          <span class="live-dot"></span>
          <strong>Live</strong>
          <span>updated {escape(stamp)}</span>
          <span class="live-version">v{version}</span>
          <span class="live-note">auto-refreshes every 30s</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _changed_card(events: list[dict]) -> None:
    items = "".join(
        f"<li><strong>{escape(str(event['event_type']).replace('_', ' ').title())}</strong>"
        f" · {escape(str(event.get('reason') or '')[:140])}</li>"
        for event in events[:4]
    )
    st.markdown(
        f"""
        <div class="changed-card">
          <div class="changed-title">Changed since the last check</div>
          <ul>{items}</ul>
          <p>The forecast, expiry ladder, and decisions below were refreshed automatically.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _simulate_sale(client, positions, actor) -> None:
    saleable = [
        row for row in positions if float(row["saleable_on_hand"]) >= 1
    ]
    if not saleable:
        st.button(
            "Simulate a sale",
            disabled=True,
            help="No saleable stock is available. Receive stock first.",
            key="simulate-sale-disabled",
        )
        return
    if not st.button(
        "Simulate a sale",
        icon=":material/point_of_sale:",
        help="Record one sale through the real ledger and watch the live cards update.",
    ):
        return
    product = saleable[0]
    try:
        result = client.stock_action(
            {
                "product_id": product["product_id"],
                "quantity": "1",
                "movement_type": "SALE",
                "request_id": f"demo-sale-{uuid4().hex}",
                "actor_name": actor["actor_name"],
                "actor_role": actor["actor_role"],
                "reason": "Demo live-loop sale",
                "daypart": "midday",
            }
        )
    except Exception as exc:
        _flash(str(exc), "error")
        st.rerun()
        return
    _flash(
        f"Recorded 1 {product['unit']} sale of {product['name']} · "
        f"{len(result.get('allocations', []))} batch allocation(s)"
    )
    st.rerun()


@st.fragment(run_every="30s")
def _live_body(client, actor):
    try:
        readiness = client.onboarding()
        positions = client.positions()
        alerts = client.expiry_alerts(3)["alerts"]
        recommendation_payload = client.recommendations()
        recommendations = recommendation_payload["recommendations"]
        buckets = client.expiry_buckets()
        products = {row["id"]: row for row in client.products()}
        activity = client.activity()
        timezone_name = client.health()["business_timezone"]
    except Exception as exc:
        show_error(exc)
        return

    version = int(recommendation_payload.get("data_version", 0))
    previous_version = st.session_state.get("live_data_version")
    previous_event_id = st.session_state.get("live_event_id", 0)
    new_events = [event for event in activity if int(event["id"]) > int(previous_event_id)]
    changed = previous_version is not None and previous_version != version
    if new_events:
        st.session_state["live_event_id"] = max(int(event["id"]) for event in new_events)
    st.session_state["live_data_version"] = version

    _show_flash()
    _live_strip(version, timezone_name)
    if changed:
        _changed_card(new_events)
    readiness_card(readiness)
    quick_left, quick_middle, quick_right = st.columns(3)
    if quick_left.button("Print daily sheet", key="today-print-sheet", icon=":material/print:"):
        st.session_state.page = "Daily sheet"
        st.rerun()
    if quick_middle.button("Purchase orders", key="today-purchasing", icon=":material/shopping_basket:"):
        st.session_state.page = "Purchasing"
        st.rerun()
    if quick_right.button("Bake plan", key="today-bakery", icon=":material/bakery_dining:"):
        st.session_state.page = "Bakery"
        st.rerun()
    action = readiness.get("next_action", {})
    if action.get("page") and action["page"] != "Today":
        if st.button(
            action.get("label", "Continue"),
            key="readiness-cta",
            type="primary",
            icon=":material/arrow_forward:",
        ):
            st.session_state.page = action["page"]
            st.rerun()
    _simulate_sale(client, positions, actor)
    st.caption(
        "Forecasts need history. Stockout-censored days are excluded from training, "
        "and every estimate is labelled."
    )

    physical = sum(float(row["physical_on_hand"]) for row in positions)
    saleable = sum(float(row["saleable_on_hand"]) for row in positions)
    expired = sum(float(row["expired_quantity"]) for row in positions)
    at_risk = sum(
        float(item["value"])
        for item in alerts
        if item["bucket"] in {"expired", "critical", "warning"}
    )
    metric_row(
        [
            (
                "Saleable units",
                number(saleable, 0),
                "Stock that can still be sold today",
                "loaf",
                "",
            ),
            (
                "Physical units",
                number(physical, 0),
                "All batches with remaining stock",
                "scale",
                "amber",
            ),
            (
                "Expired units",
                number(expired, 0),
                "Blocked from sale",
                "alert",
                "berry",
            ),
            (
                "Value at risk",
                f"${number(at_risk, 2)}",
                "Expired, critical, and warning stock",
                "chart",
                "eucalyptus",
            ),
        ]
    )

    hero(
        "Fresh from the oven",
        f"Good morning, {actor['actor_name']}.",
        f"<strong>{len(recommendations)} decisions</strong> are ready and "
        f"<strong>{len(alerts)} batches</strong> are inside the 3-day window. "
        "Let's keep the good stuff moving.",
        chips=[
            (f"{len(recommendations)} approvals waiting", "amber"),
            ("Human approval required", "blue"),
        ],
    )

    ticker_items = []
    for rec in recommendations[:8]:
        product = products.get(rec["product_id"])
        if product:
            ticker_items.append(
                (
                    product["name"],
                    f"{number(rec['quantity'], 0)} {product['unit']}",
                )
            )
    ticker(ticker_items)

    freshness_ladder(buckets.get("totals", {}), "Shelf-life runway")

    section_header(
        "Today's decisions",
        "Approve, edit, or reject each recommendation",
        "sparkle",
    )
    if not recommendations:
        st.info("No products yet. Seed the demo data or add a product.")
        return
    priority = {"MARKDOWN": 0, "BUY": 1, "BAKE": 1, "REDUCE": 2, "DONATE": 2, "HOLD": 3}
    recommendations.sort(key=lambda item: (priority.get(item["action"], 9), item["sku"]))
    for rec in recommendations[:8]:
        product = products.get(rec["product_id"])
        if product:
            _card(client, product, rec, actor)
    st.caption(
        f"{len(recommendations)} products reviewed · "
        f"{len(alerts)} batches inside the 3-day alert window"
    )
