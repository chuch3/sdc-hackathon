from __future__ import annotations

from datetime import date, timedelta
from html import escape

import streamlit as st

from dashboard.components import metric_row, note_card, number, section_header, show_error

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


def _day_label(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%b %-d")
    except ValueError:
        return value


def _card_html(card: dict) -> str:
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
    return f"""
    <div class="quest-card {escape(kind.lower())}" tabindex="0">
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
    """


def _day_html(day: dict) -> str:
    risk = day.get("risk_level", "calm")
    tone = RISK_TONE.get(risk, "slate")
    kpis = day.get("kpis", {})
    projection = day.get("projection", {})
    cards = "".join(_card_html(card) for card in day.get("cards", []))
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
    if cards:
        empty = ""
    elif kpis.get("stockout_risk") in {"high", "medium"}:
        empty = '<div class="quest-empty">No new action; the risk is flagged above</div>'
    else:
        empty = '<div class="quest-empty">Nothing to do</div>'
    return f"""
    <div class="quest-day">
      <div class="quest-day-head">
        <div class="quest-weekday">{escape(day.get('weekday', ''))}</div>
        <div class="quest-date">{escape(_day_label(day.get('date', '')))}</div>
        <span class="pill {tone}">{escape(RISK_LABEL.get(risk, risk))}</span>
      </div>
      <div class="quest-day-stats">{stock}</div>
      {f'<ul class="quest-orders">{orders}</ul>' if orders else ''}
      {cards or empty}
    </div>
    """


def _progress_html(summary: dict) -> str:
    days = int(summary.get("days", 0) or 0)
    covered = int(summary.get("plan_coverage_days", 0) or 0)
    percent = int(round(summary.get("quest_progress", 0) * 100))
    return f"""
    <div class="quest-progress">
      <div class="quest-progress-head">
        <span>Plan coverage</span>
        <strong>{covered} of {days} days with a clean plan</strong>
      </div>
      <div class="quest-bar"><span style="width:{percent}%"></span></div>
    </div>
    """


def _badges_html(badges: list[dict]) -> str:
    chips = "".join(
        f"<span class='quest-badge{' earned' if badge.get('earned') else ''}' "
        f"title='{escape(badge.get('detail', ''))}'>{escape(badge.get('label', ''))}</span>"
        for badge in badges
    )
    return f'<div class="quest-badges">{chips}</div>'


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
    return f"""
    <div class="heat-map">
      <div class="heat-grid">{"".join(cells)}</div>
      <div class="heat-legend"><span>Less</span>{legend}<span>More</span></div>
    </div>
    """


def render(client, actor):
    try:
        plan = client.planner_week()
    except Exception as exc:
        show_error(exc)
        return

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

    section_header(
        "Weekly quest board",
        f"{plan.get('start_date')} to {plan.get('end_date')} · planned from "
        f"{plan.get('as_of')} · {plan.get('engine')} engine",
        "wheat",
    )
    st.markdown(_progress_html(summary), unsafe_allow_html=True)
    st.markdown(_badges_html(plan.get("badges", [])), unsafe_allow_html=True)

    days = plan.get("days", [])
    if not days:
        st.info("No plan available yet. Add products and sales history first.")
        return

    expand_all = st.toggle(
        "Expand every card",
        value=False,
        key="quest_expand_all",
        help="Hover a card to peek at its reasoning, or turn this on to open every card.",
    )
    board_class = "quest-board expand-all" if expand_all else "quest-board"
    columns = st.columns(len(days))
    for column, day in zip(columns, days):
        column.markdown(f'<div class="{board_class}">{_day_html(day)}</div>', unsafe_allow_html=True)

    st.caption(
        "Read-only projection: the board changes nothing in the ledger. Approve the real "
        "actions on the Actions page."
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

    for assumption in plan.get("assumptions", []):
        note_card(assumption, icon_name="leaf", tone="sage")
