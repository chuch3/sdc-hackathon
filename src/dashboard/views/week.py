from __future__ import annotations

from datetime import date, timedelta
from html import escape

import streamlit as st

from dashboard.components import metric_row, note_card, number, section_header, show_error
from dashboard.quest_modal import QUEST_MODAL_HTML

CARD_LABEL = {
    "SELL_FIRST": "Sell first",
    "MARKDOWN": "Markdown",
    "DONATE": "Donate",
    "WRITE_OFF": "Write off",
    "RECEIVE_ORDER": "Receive order",
    "STOCKOUT": "Stockout",
    "BUY": "Buy",
    "BAKE": "Bake",
    "HOLD": "Hold",
    "DATA_WARNING": "Check data",
}
CARD_TONE = {
    "SELL_FIRST": "amber",
    "MARKDOWN": "orange",
    "DONATE": "green",
    "WRITE_OFF": "red",
    "RECEIVE_ORDER": "teal",
    "STOCKOUT": "red",
    "BUY": "blue",
    "BAKE": "amber",
    "HOLD": "slate",
    "DATA_WARNING": "slate",
}
RISK_TONE = {"calm": "green", "busy": "amber", "risky": "red"}
RISK_LABEL = {"calm": "calm", "busy": "busy", "risky": "risky"}
HEAT_LEVELS = 5
VISIBLE_CARDS = 3


def _day_label(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%b %-d")
    except ValueError:
        return value


def _markup(value: str) -> str:
    """Strip indentation and blank lines so Markdown keeps one raw HTML block."""
    lines = (line.strip() for line in value.strip().splitlines())
    return "\n".join(line for line in lines if line)


def _card_html(card: dict, overflow: bool = False) -> str:
    kind = card.get("kind", "HOLD")
    tone = CARD_TONE.get(kind, "slate")
    label = CARD_LABEL.get(kind, kind.title())
    quantity = float(card.get("quantity", 0) or 0)
    unit = card.get("unit") or ""
    meta = []
    if card.get("deadline"):
        meta.append(f"by {_day_label(card['deadline'])}")
    meta.append(f"{number(card.get('confidence', 0) * 100)}% confidence")
    why = "".join(f"<li>{escape(line)}</li>" for line in card.get("why", []))
    calculation = card.get("calculation") or {}
    rows = "".join(
        f"<li><span>{escape(str(key))}</span><strong>{escape(str(round(float(value), 2)))}</strong></li>"
        for key, value in calculation.items()
    )
    impact = card.get("impact") or ""
    overflow_class = " quest-card-overflow" if overflow else ""
    return _markup(f"""
    <div class="quest-card {escape(kind.lower())}{overflow_class}" tabindex="0">
      <div class="quest-card-top">
        <span class="pill {tone}">{escape(label)}</span>
        <span class="quest-qty">{number(quantity, 1)} {escape(unit)}</span>
      </div>
      <div class="quest-card-title">{escape(card.get('product_name') or 'Weekly plan')}</div>
      <div class="quest-card-summary">{escape(card.get('summary', ''))}</div>
      <div class="quest-card-extra">
        <div class="quest-card-meta">{escape(' · '.join(meta))}</div>
        <ul class="quest-why-list">{why}</ul>
        {f'<p class="quest-impact">{escape(impact)}</p>' if impact else ''}
        {f'<ul class="quest-calc">{rows}</ul>' if rows else ''}
      </div>
    </div>
    """)


def _day_html(day: dict) -> str:
    risk = day.get("risk_level", "calm")
    tone = RISK_TONE.get(risk, "slate")
    kpis = day.get("kpis", {})
    projection = day.get("projection", {})
    day_cards = day.get("cards", [])
    cards = "".join(
        _card_html(card, overflow=index >= VISIBLE_CARDS)
        for index, card in enumerate(day_cards)
    )
    more = ""
    if len(day_cards) > VISIBLE_CARDS:
        more = (
            f'<button type="button" class="quest-more" '
            f'data-day="{escape(day.get("weekday", ""))}" '
            f'data-date="{escape(day.get("date", ""))}" '
            f'aria-haspopup="dialog" aria-label="Show all {len(day_cards)} tasks for '
            f'{escape(day.get("weekday", ""))}">'
            f"+{len(day_cards) - VISIBLE_CARDS} more tasks "
            f"\u00b7 show all {len(day_cards)}</button>"
        )
    orders = "".join(
        f"<li>#{order['purchase_order_id']} · {number(float(order['total_quantity']), 1)} units"
        f"{' · overdue' if order.get('overdue') else ''}</li>"
        for order in day.get("orders_due", [])
    )
    stock = (
        f"<div class='quest-day-stat'>Stock {number(float(projection.get('starting_stock', 0)), 0)}"
        f" → {number(float(projection.get('ending_stock', 0)), 0)}</div>"
        f"<div class='quest-day-stat'>Sales {number(float(projection.get('expected_sales', 0)), 0)}"
        f" · arrivals {number(float(projection.get('arrivals', 0)), 0)}</div>"
        f"<div class='quest-day-stat'>At risk ${number(float(kpis.get('value_at_risk', 0)), 2)}"
        f" · waste ${number(float(kpis.get('expected_waste', 0)), 2)}</div>"
    )
    market = day.get("market_day")
    market_html = ""
    if market:
        market_html = (
            f'<div class="market-day"><strong>Market day · {escape(market.get("label", ""))}</strong>'
            f' · ×{escape(str(market.get("demand_multiplier", "1")))}'
            f'{" · " + escape(market.get("note", "")) if market.get("note") else ""}</div>'
        )
    if cards:
        empty = ""
    elif kpis.get("stockout_risk") in {"high", "medium"}:
        empty = '<div class="quest-empty">No new action; the risk is flagged above</div>'
    else:
        empty = '<div class="quest-empty">Nothing to do</div>'
    return _markup(f"""
    <div class="quest-day">
      <div class="quest-day-head">
        <div class="quest-weekday">{escape(day.get('weekday', ''))}</div>
        <div class="quest-date">{escape(_day_label(day.get('date', '')))}</div>
        <span class="pill {tone}">{escape(RISK_LABEL.get(risk, risk))}</span>
      </div>
      <div class="quest-day-stats">{stock}</div>
      {market_html}
      {f'<ul class="quest-orders">{orders}</ul>' if orders else ''}
      {cards or empty}
      {more}
    </div>
    """)


def _workload_html(plan: dict, summary: dict) -> str:
    """One horizontal bar: the week's task load, split by day, plus completion."""
    days = plan.get("days", [])
    total = int(summary.get("cards", 0) or 0)
    clean = int(summary.get("plan_coverage_days", 0) or 0)
    day_count = int(summary.get("days", len(days)) or 0)
    percent = int(round(float(summary.get("quest_progress", 0) or 0) * 100))

    kind_counts: dict[str, int] = {}
    segments = []
    for day in days:
        cards = day.get("cards", [])
        risk = day.get("risk_level", "calm")
        for card in cards:
            kind = card.get("kind", "HOLD")
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        count = len(cards)
        label = escape(day.get("weekday", "")[:3])
        segments.append(
            f'<span class="quest-load-seg {escape(risk)}" style="flex:{count + 0.4:.2f}" '
            f'title="{escape(day.get("weekday", ""))} {escape(day.get("date", ""))}: '
            f'{count} task{"s" if count != 1 else ""}">'
            f"<b>{label}</b><i>{count if count else '·'}</i></span>"
        )

    legend = "".join(
        f'<span class="pill {CARD_TONE.get(kind, "slate")}">'
        f"{escape(CARD_LABEL.get(kind, kind.title()))} {count}</span>"
        for kind, count in sorted(kind_counts.items(), key=lambda item: (-item[1], item[0]))
    )

    return _markup(f"""
    <div class="quest-workload">
      <div class="quest-workload-head">
        <span>Weekly workload</span>
        <strong>{total} tasks · {percent}% covered</strong>
      </div>
      <div class="quest-bar"><span style="width:{percent}%"></span></div>
      <div class="quest-load">{"".join(segments)}</div>
      <div class="quest-workload-foot">
        <span class="quest-workload-note">{clean} of {day_count} days run a clean plan</span>
        <span class="quest-workload-legend">{legend}</span>
      </div>
    </div>
    """)


def _level(intensity: float) -> int:
    if intensity <= 0:
        return 0
    return max(1, min(HEAT_LEVELS, int(round(intensity * HEAT_LEVELS))))


def _calendar_html(calendar: dict) -> str:
    """Contribution-style heatmap: one column per week, one row per weekday."""
    buckets = calendar.get("days_detail", [])
    if not buckets:
        return ""
    by_date = {bucket["date"]: bucket for bucket in buckets}
    start = date.fromisoformat(calendar["start_date"])
    end = date.fromisoformat(calendar["end_date"])
    grid_start = start - timedelta(days=start.weekday())
    weeks: list[list[dict | None]] = []
    cursor = grid_start
    while cursor <= end:
        week = []
        for offset in range(7):
            day = cursor + timedelta(days=offset)
            bucket = by_date.get(day.isoformat())
            week.append(bucket if day <= end else None)
        weeks.append(week)
        cursor += timedelta(days=7)

    cells = []
    for week in weeks:
        column = []
        for bucket in week:
            if bucket is None:
                column.append('<div class="heat-cell empty"></div>')
                continue
            level = _level(float(bucket.get("intensity", 0) or 0))
            flags = []
            if bucket.get("has_waste"):
                flags.append("waste")
            if bucket.get("has_stockout"):
                flags.append("stockout")
            title = (
                f"{_day_label(bucket['date'])} · "
                f"{number(bucket.get('sales', 0), 0)} sold · "
                f"{number(bucket.get('waste', 0), 0)} wasted · "
                f"{number(bucket.get('donations', 0), 0)} donated · "
                f"{number(bucket.get('decisions', 0), 0)} decisions"
            )
            column.append(
                f'<div class="heat-cell lv{level} {" ".join(flags)}" title="{escape(title)}"></div>'
            )
        cells.append(f'<div class="heat-week">{"".join(column)}</div>')

    legend = "".join(
        f'<span class="heat-cell lv{level}"></span>' for level in range(HEAT_LEVELS + 1)
    )
    return _markup(f"""
    <div class="heat-map">
      <div class="heat-grid">{"".join(cells)}</div>
      <div class="heat-legend"><span>Less</span>{legend}<span>More</span></div>
    </div>
    """)


def render(client, actor):
    try:
        plan = client.planner_week()
        markets = client.market_days(plan.get("start_date"), plan.get("end_date"))
    except Exception as exc:
        show_error(exc)
        return

    with st.expander("Market days", expanded=False):
        st.caption("A market day multiplies forecast demand for its date and appears on this board.")
        with st.form("market-day-form", clear_on_submit=True):
            add_date = st.date_input("Market date", value=date.fromisoformat(plan["start_date"]))
            add_label = st.text_input("Label", value="Saturday market")
            add_multiplier = st.number_input("Demand multiplier", min_value=0.1, value=1.2, step=0.05)
            add_note = st.text_input("Operational note", value="")
            if st.form_submit_button("Add market day", type="primary"):
                try:
                    client.create_market_day({"market_date": add_date.isoformat(), "label": add_label, "demand_multiplier": str(add_multiplier), "note": add_note})
                    st.rerun()
                except Exception as exc:
                    show_error(exc)
        for market in markets:
            left, right = st.columns([5, 1])
            left.caption(f"{market['market_date']} · {market['label']} · ×{market['demand_multiplier']} {market.get('note', '')}")
            if right.button("Remove", key=f"remove-market-{market['id']}"):
                try:
                    client.delete_market_day(market["id"])
                    st.rerun()
                except Exception as exc:
                    show_error(exc)

    summary = plan.get("weekly_summary", {})
    metric_row(
        [
            (
                "Cost at risk",
                f"${number(float(summary.get('cost_at_risk', 0)), 2)}",
                "Stock that expires inside the plan window",
                "chart",
                "eucalyptus",
            ),
            (
                "Expected waste",
                f"${number(float(summary.get('expected_waste', 0)), 2)}",
                "Cost of stock the plan expects to expire",
                "alert",
                "berry",
            ),
            (
                "Cost avoided (est.)",
                f"${number(float(summary.get('estimated_cost_avoided', 0)), 2)}",
                "Cost of near-expiry stock that sells in time",
                "leaf",
                "sage",
            ),
            (
                "Stockout days",
                number(float(summary.get("stockout_days", 0)), 0),
                f"{number(float(summary.get('waste_free_days', 0)), 0)} waste-free days",
                "clock",
                "amber",
            ),
        ]
    )

    try:
        calendar = client.activity_calendar()
    except Exception:
        calendar = {}
    if calendar.get("days_detail"):
        section_header(
            "Activity calendar",
            f"{calendar.get('start_date')} to {calendar.get('end_date')} · units sold, "
            "wasted, donated, and decisions recorded",
            "chart",
        )
        st.markdown(_calendar_html(calendar), unsafe_allow_html=True)
        st.caption(
            "Darker squares mean a busier day. A red corner means stock was wasted that "
            "day; an amber corner means a stockout was recorded."
        )

    section_header(
        "Weekly quest board",
        f"{plan.get('start_date')} to {plan.get('end_date')} · planned from "
        f"{plan.get('as_of')} · {plan.get('engine')} engine",
        "wheat",
    )
    days = plan.get("days", [])
    if not days:
        st.markdown(_workload_html(plan, summary), unsafe_allow_html=True)
        st.info("No plan available yet. Add products and sales history first.")
        return

    st.markdown(_workload_html(plan, summary), unsafe_allow_html=True)

    expand_all = st.toggle(
        "Show every task's reasoning",
        value=False,
        key="quest_expand_all",
        help="The board shows each task summary. Turn this on to open the reasoning, "
        "impact, and calculation for every card.",
    )
    board_class = "quest-board expand-all show-all" if expand_all else "quest-board"
    columns = st.columns(len(days))
    for column, day in zip(columns, days):
        column.markdown(f'<div class="{board_class}">{_day_html(day)}</div>', unsafe_allow_html=True)

    st.html(QUEST_MODAL_HTML, unsafe_allow_javascript=True)

    st.caption(
        "Read-only projection: the board changes nothing in the ledger. Approve the real "
        "actions on the Actions page."
    )

    for assumption in plan.get("assumptions", []):
        note_card(assumption, icon_name="leaf", tone="sage")
