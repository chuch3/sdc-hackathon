from __future__ import annotations

from decimal import Decimal
from html import escape

import streamlit as st

from dashboard.art import category_icon, icon

ACTION_STYLE = {
    "BUY": ("Buy", "blue"),
    "BAKE": ("Bake", "amber"),
    "MARKDOWN": ("Markdown", "orange"),
    "DONATE": ("Donate", "green"),
    "WASTE": ("Write off", "red"),
    "WRITE_OFF": ("Write off", "red"),
    "REDUCE": ("Reduce", "orange"),
    "HOLD": ("Hold", "slate"),
}

LADDER_TONES = ("expired", "critical", "warning", "healthy")
LADDER_LABELS = {
    "expired": "Expired",
    "critical": "Critical",
    "warning": "Warning",
    "healthy": "Healthy",
}


def pill(label: str, tone: str = "slate") -> str:
    return f'<span class="pill {tone}">{escape(str(label))}</span>'


def action_pill(action: str) -> str:
    label, tone = ACTION_STYLE.get(action, (action.title(), "slate"))
    return pill(label, tone)


def risk_pill(risk: str) -> str:
    tone = {
        "expired": "red",
        "critical": "red",
        "warning": "orange",
        "healthy": "green",
    }.get(risk, "slate")
    return pill(risk.title(), tone)


def status_pill(status: str) -> str:
    tone = {
        "DRAFT": "slate",
        "APPROVED": "blue",
        "RECEIVED": "green",
        "CANCELLED": "red",
    }.get(status, "slate")
    return pill(status.title(), tone)


def number(value, places: int = 0) -> str:
    try:
        return f"{Decimal(str(value)):,.{places}f}"
    except Exception:
        return str(value)


def show_error(exc: Exception) -> None:
    detail = getattr(exc, "detail", str(exc))
    st.error(detail)


def page_header(
    title: str,
    subtitle: str,
    business_date: str,
    actor: dict,
    icon_name: str = "wheat",
) -> None:
    role = escape(str(actor.get("actor_role", "viewer")).title())
    st.markdown(
        f"""
        <div class="page-head">
          <div class="page-copy">
            <div class="eyebrow">{icon(icon_name, 15)} Buns At Work!</div>
            <h1>{escape(title)}</h1>
            <p>{escape(subtitle)}</p>
          </div>
          <div class="page-meta">
            <span class="meta-chip"><span class="meta-dot"></span>{escape(business_date)}</span>
            <span class="meta-chip role-chip">{role}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(
    title: str,
    caption: str | None = None,
    icon_name: str | None = None,
) -> None:
    note = f'<p class="section-note">{escape(caption)}</p>' if caption else ""
    badge = f'<span class="section-icon">{icon(icon_name, 16)}</span>' if icon_name else ""
    st.markdown(
        f'<div class="section-head"><div class="section-title">{badge}'
        f"<h3>{escape(title)}</h3></div>{note}</div>",
        unsafe_allow_html=True,
    )


def metric_row(items: list[tuple]) -> None:
    columns = st.columns(len(items))
    for column, item in zip(columns, items):
        label, value, help_text = item[:3]
        icon_name = item[3] if len(item) > 3 else "sparkle"
        tone = item[4] if len(item) > 4 else ""
        note = escape(help_text) if help_text else "&nbsp;"
        column.markdown(
            f"""
            <div class="metric-card">
              <div class="metric-top">
                <span class="metric-icon {escape(tone)}">{icon(icon_name, 18)}</span>
                <span class="metric-label">{escape(label)}</span>
              </div>
              <div class="metric-value">{escape(str(value))}</div>
              <div class="metric-help">{note}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def hero(
    kicker: str,
    title: str,
    body_html: str,
    chips: list[tuple[str, str]] | None = None,
    art: bool = True,
) -> None:
    from dashboard.art import hero_art

    chip_html = "".join(pill(label, tone) for label, tone in (chips or []))
    art_html = f'<div class="hero-art">{hero_art()}</div>' if art else ""
    st.markdown(
        f"""
        <div class="hero-bake">
          <div class="hero-copy">
            <span class="hero-kicker">{icon("flame", 14)} {escape(kicker)}</span>
            <div class="hero-title">{escape(title)}</div>
            <p class="hero-body">{body_html}</p>
            <div class="hero-chips">{chip_html}</div>
          </div>
          {art_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def ticker(items: list[tuple[str, str]]) -> None:
    if not items:
        return
    entries = "".join(
        f'<span class="ticker-item"><strong>{escape(name)}</strong> · {escape(qty)}</span>'
        for name, qty in items
    )
    st.markdown(
        f"""
        <div class="bake-ticker" aria-hidden="true">
          <span class="ticker-label">{icon("oven", 13)} On the bench</span>
          <div class="ticker-viewport">
            <div class="ticker-track">{entries}{entries}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def freshness_ladder(totals: dict, title: str = "Freshness mix") -> None:
    values = {}
    for tone in LADDER_TONES:
        try:
            values[tone] = max(float(totals.get(tone, 0) or 0), 0.0)
        except (TypeError, ValueError):
            values[tone] = 0.0
    total = sum(values.values())
    if total <= 0:
        return
    segments = "".join(
        f'<span class="ladder-seg {tone}" style="width:{values[tone] / total * 100:.1f}%"></span>'
        for tone in LADDER_TONES
    )
    legend = "".join(
        f'<span class="ladder-key"><span class="ladder-dot {tone}"></span>'
        f"{LADDER_LABELS[tone]} <strong>{number(values[tone], 0)}</strong></span>"
        for tone in LADDER_TONES
    )
    st.markdown(
        f"""
        <div class="ladder">
          <div class="ladder-head">
            <span class="ladder-title">{escape(title)}</span>
            <span class="ladder-total">{number(total, 0)} units tracked</span>
          </div>
          <div class="ladder-bar">{segments}</div>
          <div class="ladder-legend">{legend}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, body: str, icon_name: str = "basket") -> None:
    st.markdown(
        f"""
        <div class="empty-state">
          <div class="empty-art">{icon(icon_name, 30)}</div>
          <h4>{escape(title)}</h4>
          <p>{escape(body)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def note_card(
    text: str,
    icon_name: str = "leaf",
    tone: str = "amber",
    title: str | None = None,
) -> None:
    heading = f"<strong>{escape(title)}</strong> " if title else ""
    extra = " sage" if tone == "sage" else ""
    st.markdown(
        f'<div class="note-card{extra}">{icon(icon_name, 17)}'
        f"<div>{heading}{escape(text)}</div></div>",
        unsafe_allow_html=True,
    )


def product_line(name: str, meta: str, category: str | None = None) -> str:
    return (
        f'<div class="product-line"><span class="product-icon">'
        f'{icon(category_icon(category), 18)}</span><div>'
        f'<div class="product-name">{escape(name)}</div>'
        f'<div class="product-meta">{escape(meta)}</div></div></div>'
    )


def confidence(value: float) -> str:
    try:
        pct = max(0.0, min(float(value), 1.0)) * 100
    except (TypeError, ValueError):
        pct = 0.0
    return f'<div class="confidence"><span style="width:{pct:.0f}%"></span></div>'


READINESS_TITLE = {
    "no_products": "Add products to begin",
    "no_sales": "Waiting for sales history",
    "thin_history": "Learning from a short history",
    "ready": "Forecast ready",
    "live": "Live today",
}


def readiness_card(data: dict) -> None:
    stage = str(data.get("stage", "no_products"))
    tone = "green" if stage in {"ready", "live"} else "amber"
    if stage == "no_products":
        tone = "red"
    checks = "".join(
        f'<span class="readiness-check {"ok" if item.get("ok") else "warn"}">'
        f'{icon("check" if item.get("ok") else "alert", 12)} '
        f'{escape(str(item.get("label", "")))}: {escape(str(item.get("detail", "")))}</span>'
        for item in data.get("checks", [])
    )
    st.markdown(
        f"""
        <div class="readiness-card {tone}">
          <div class="readiness-head">
            <span class="readiness-title">{escape(READINESS_TITLE.get(stage, stage.replace("_", " ").title()))}</span>
            <span class="readiness-stage">{escape(stage.replace("_", " ").upper())}</span>
          </div>
          <p>{escape(str(data.get("next_action", {}).get("reason", "")))}</p>
          <div class="readiness-checks">{checks}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_row(label: str, value: str) -> str:
    return (
        f'<div class="status-row"><span>{escape(label)}</span>'
        f"<span>{escape(value)}</span></div>"
    )


def actor_payload(session) -> dict:
    return {
        "actor_name": session.get("actor_name", "Demo Owner"),
        "actor_role": session.get("actor_role", "owner"),
        "reason": session.get("reason", "Dashboard decision"),
    }
