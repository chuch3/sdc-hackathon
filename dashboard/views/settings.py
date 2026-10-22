from __future__ import annotations

import streamlit as st

from dashboard.components import note_card, section_header, show_error, status_row


def render(client, actor):
    try:
        health = client.health()
        orbyte = client.orbyte_status()
        recs = client.recommendations()
    except Exception as exc:
        show_error(exc)
        return
    left, right = st.columns(2)
    with left:
        section_header("Connection", "Live API and runtime", "gear")
        rows = "".join(
            [
                status_row("API", client.base_url),
                status_row("Business date", health["business_date"]),
                status_row("Timezone", health["business_timezone"]),
                status_row("Forecast engine", recs["engine"]),
                status_row("Role", actor["actor_role"]),
            ]
        )
        st.markdown(f'<div class="status-grid">{rows}</div>', unsafe_allow_html=True)
    with right:
        section_header("Orbyte", "Workspace link", "sparkle")
        state = "Configured" if orbyte["configured"] else "Not configured"
        st.markdown(
            f'<div class="status-grid">{status_row("Integration", state)}</div>',
            unsafe_allow_html=True,
        )
        note_card(orbyte["note"], icon_name="sparkle", tone="sage")
        if orbyte["configured"]:
            st.link_button(
                "Open Orbyte",
                "https://orbyte-xyz.alphareds.com",
                icon=":material/open_in_new:",
            )
    section_header("Demo seed", "Rebuild the fictional shop data", "wheat")
    st.code(
        "cd backend\n"
        "uv run python -m alembic upgrade head\n"
        "uv run python -m scripts.seed\n"
        "uv run python -m scripts.start",
        language="bash",
    )
    note_card(
        "The dashboard calls HTTP only. It never opens or edits SQLite directly.",
        icon_name="check",
        tone="sage",
    )
