from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import streamlit as st

from dashboard.components import note_card, section_header, show_error, status_row

MAPPING_FIELDS = (
    ("date", "Date column"),
    ("sku", "SKU column"),
    ("quantity", "Quantity column"),
    ("daypart", "Daypart column"),
    ("stockout", "Stockout flag column"),
)


def _demo_csv(products: list[dict], business_date: str) -> str:
    start = date.fromisoformat(business_date)
    skus = [row["sku"] for row in products[:4]] or ["MILK-001"]
    rows = ["business_date,item_code,units,part_of_day,stock_out"]
    for offset in range(16, 0, -1):
        day = start - timedelta(days=offset)
        raw_date = (
            day.strftime("%d/%m/%Y") if offset % 3 == 0 else day.isoformat()
        )
        for index, sku in enumerate(skus):
            quantity = 3 + (offset + index) % 4
            daypart = "morning" if index % 2 == 0 else "midday"
            rows.append(f"{raw_date},{sku},{quantity},{daypart},false")
    rows.append(rows[-1])
    rows.append(f"{start - timedelta(days=2)},UNKNOWN-001,2,midday,false")
    rows.append(f"{start - timedelta(days=1)},{skus[0]},0,evening,true")
    return "\n".join(rows) + "\n"


def _import_panel(client, health, products):
    section_header("Import sales", "Bring a messy CSV up to forecast quality", "upload")
    sample = _demo_csv(products, health["business_date"])
    st.download_button(
        "Download sample CSV",
        data=sample,
        file_name="freshstock_sales_sample.csv",
        mime="text/csv",
        icon=":material/download:",
    )
    st.caption(
        "Aliases such as business_date, item_code, units, part_of_day and stock_out are "
        "detected automatically. Dates can mix ISO and day-first formats."
    )
    uploaded = st.file_uploader("Upload a sales CSV", type=["csv"], key="sales-import-file")
    if uploaded is not None:
        st.session_state["sales_import_csv"] = uploaded.getvalue().decode("utf-8-sig")
    if st.button("Load the demo CSV", icon=":material/experiment:"):
        st.session_state["sales_import_csv"] = sample
        st.session_state.pop("sales_import_preview", None)
        st.session_state.pop("sales_import_result", None)
        st.rerun()
    csv_text = st.session_state.get("sales_import_csv", "")
    if not csv_text:
        return

    columns = csv_text.lstrip("\ufeff").splitlines()[0].split(",")
    mapping: dict[str, str | None] = {}
    with st.expander("Column mapping", expanded=False):
        for key, label in MAPPING_FIELDS:
            choice = st.selectbox(
                label,
                ["Auto-detect", *columns],
                key=f"import-map-{key}",
            )
            mapping[key] = None if choice == "Auto-detect" else choice

    if st.button("Preview import", type="primary", icon=":material/preview:"):
        try:
            preview = client.preview_sales_import(csv_text, mapping)
        except Exception as exc:
            show_error(exc)
            return
        st.session_state["sales_import_preview"] = preview
        st.session_state["sales_import_mapping"] = mapping
        st.session_state["sales_import_request_id"] = f"demo-{uuid4().hex}"

    result = st.session_state.get("sales_import_result")
    if result:
        st.success(
            f"Imported {result['imported_rows']} row(s) in {result['batches_created']} "
            f"closed history batch(es). Stock on hand is unchanged."
        )
        st.caption(
            f"Request {result['request_id']} · data version {result['data_version']} · "
            f"{result['invalid_rows']} invalid row(s) skipped."
        )

    preview = st.session_state.get("sales_import_preview")
    if not preview:
        return
    row_counts = st.columns(4)
    row_counts[0].metric("Valid rows", preview["valid_rows"])
    row_counts[1].metric("Invalid rows", preview["invalid_rows"])
    row_counts[2].metric("Duplicate rows", preview["duplicate_rows"])
    row_counts[3].metric("Usable days", preview["valid_days"])
    st.caption(
        f"Window {preview['date_start'] or '—'} to {preview['date_end'] or '—'} · "
        f"{preview['stockout_rows']} stockout marker(s) · "
        f"{len(preview['unknown_skus'])} unknown SKU(s)."
    )
    if preview["issues"]:
        st.dataframe(
            preview["issues"],
            hide_index=True,
            use_container_width=True,
        )
    if preview["can_commit"]:
        if st.button(
            f"Import {preview['valid_rows']} valid row(s)",
            type="primary",
            icon=":material/publish:",
        ):
            try:
                result = client.commit_sales_import(
                    csv_text,
                    st.session_state["sales_import_request_id"],
                    st.session_state.get("sales_import_mapping", {}),
                )
            except Exception as exc:
                show_error(exc)
                return
            st.session_state["sales_import_result"] = result
            st.session_state.pop("sales_import_preview", None)
            st.rerun()
    else:
        st.warning("No valid rows yet. Fix the reported issues and preview again.")


def render(client, actor):
    try:
        health = client.health()
        orbyte = client.orbyte_status()
        recs = client.recommendations()
        readiness = client.onboarding()
        products = client.products()
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
    section_header("Data check", "What the forecast can see right now", "check")
    rows = "".join(
        status_row(
            check["label"],
            ("OK · " if check["ok"] else "Missing · ") + check["detail"],
        )
        for check in readiness.get("checks", [])
    )
    st.markdown(f'<div class="status-grid">{rows}</div>', unsafe_allow_html=True)
    st.caption(
        f"Stage: {readiness['stage']} · "
        f"{readiness['products_ready']} of {readiness['products_active']} products ready · "
        f"{readiness['censored_days']} stockout-censored day(s) excluded."
    )
    _import_panel(client, health, products)
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
