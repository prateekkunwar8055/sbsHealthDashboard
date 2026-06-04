from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.data_sources import WorkbookSource, download_google_sheet, uploaded_workbook
from dashboard.metrics import (
    by_hospital,
    cost_mix,
    duplicate_patients,
    executive_kpis,
    monthly,
    ranked_dimension,
    target_achievement,
)
from dashboard.parsing import build_dashboard_data


APP_TITLE = "Hospital BI Dashboard"


def get_auth_credentials() -> tuple[str, str] | None:
    auth = st.secrets.get("auth")
    if isinstance(auth, dict) and auth.get("user") and auth.get("pass"):
        return auth["user"], auth["pass"]
    return None


def authenticate() -> None:
    credentials = get_auth_credentials()
    if credentials is None:
        expected_username, expected_password = "admin", "admin"
        st.sidebar.info("No Streamlit auth secrets found. Using fallback credentials: admin / admin")
    else:
        expected_username, expected_password = credentials

    username = st.sidebar.text_input("Username", key="auth_username")
    password = st.sidebar.text_input("Password", type="password", key="auth_password")
    if not username or not password:
        st.sidebar.warning("Enter your credentials to continue.")
        st.stop()
    if username != expected_username or password != expected_password:
        st.sidebar.error("Invalid username or password.")
        st.stop()


st.set_page_config(page_title=APP_TITLE, page_icon=":bar_chart:", layout="wide")


def format_money(value: float) -> str:
    if abs(value) >= 10_000_000:
        return f"Rs {value / 10_000_000:,.2f} Cr"
    if abs(value) >= 100_000:
        return f"Rs {value / 100_000:,.2f} L"
    return f"Rs {value:,.0f}"


def format_pct(value: float) -> str:
    return f"{value * 100:,.1f}%"


def default_sources() -> dict[str, Path]:
    downloads = Path.home() / "Downloads"
    return {
        "Balajee": downloads / "IPD Balajee .xlsx",
        "SBS Andheri": downloads / "IPD SBS Andheri.xlsx",
        "Doctors": downloads / "DOCTORS LIST.xlsx",
    }


def load_source_from_controls(label: str, default_path: Path) -> WorkbookSource | None:
    mode = st.radio(
        f"{label} source",
        ["Default local file", "Upload XLSX", "Public Google Sheet link"],
        horizontal=False,
        key=f"{label}_source_mode",
    )
    if mode == "Default local file":
        if default_path.exists():
            return WorkbookSource(
                name=default_path.name,
                content=default_path.read_bytes(),
                loaded_at=datetime.now(),
                source_type="local_file",
            )
        st.warning(f"Default file not found: {default_path}")
        return None
    if mode == "Upload XLSX":
        upload = st.file_uploader(f"Upload {label} workbook", type=["xlsx"], key=f"{label}_upload")
        if upload:
            source = uploaded_workbook(upload, upload.name)
            return source
        return None

    url = st.text_input(f"{label} public Google Sheet URL", key=f"{label}_sheet_url")
    if not url:
        return None
    try:
        source = download_google_sheet(url, label)
        return source
    except Exception as exc:  # pragma: no cover - surfaced in UI
        st.error(f"Could not load {label}: {exc}")
        return None


def install_auto_refresh(enabled: bool, minutes: int) -> None:
    if not enabled:
        return
    milliseconds = int(minutes * 60 * 1000)
    st.html(
        f"""
        <script>
          window.setTimeout(function() {{
            window.parent.location.reload();
          }}, {milliseconds});
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def render_source_status(data: Any, sources: dict[str, WorkbookSource | None]) -> None:
    rows = []
    for role, source in sources.items():
        audit = data.tab_audit[data.tab_audit["role"].eq(role)] if not data.tab_audit.empty else pd.DataFrame()
        rows.append(
            {
                "source": role,
                "workbook": source.name if source else "Not loaded",
                "type": source.source_type.replace("_", " ") if source else "",
                "loaded_at": source.loaded_at.strftime("%d %b %Y %H:%M:%S") if source else "",
                "tabs_found": int(audit["sheet"].nunique()) if not audit.empty else 0,
                "non_empty_tabs": int((~audit["empty"]).sum()) if not audit.empty else 0,
                "tab_rows": int(audit["rows"].sum()) if not audit.empty else 0,
                "warnings": sum(1 for warning in data.warnings if role.split()[0] in warning),
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


@st.cache_data(show_spinner="Reading workbooks...")
def cached_dashboard_data(
    balajee_name: str | None,
    balajee_content: bytes | None,
    sbs_name: str | None,
    sbs_content: bytes | None,
    doctors_name: str | None,
    doctors_content: bytes | None,
    refresh_token: int,
) -> Any:
    del refresh_token
    return build_dashboard_data(
        (balajee_name, balajee_content) if balajee_name and balajee_content else None,
        (sbs_name, sbs_content) if sbs_name and sbs_content else None,
        (doctors_name, doctors_content) if doctors_name and doctors_content else None,
    )


def apply_filters(ipd: pd.DataFrame) -> pd.DataFrame:
    if ipd.empty:
        return ipd
    with st.sidebar.expander("Dashboard filters", expanded=True):
        hospitals = st.multiselect(
            "Hospitals",
            sorted(ipd["hospital"].dropna().unique()),
            default=sorted(ipd["hospital"].dropna().unique()),
        )
        months = st.multiselect(
            "Months",
            list(ipd.sort_values("month_order")["month"].dropna().unique()),
            default=list(ipd.sort_values("month_order")["month"].dropna().unique()),
        )
        tpas = st.multiselect(
            "TPA / Cash",
            sorted(ipd.get("TPA", pd.Series(dtype=str)).dropna().astype(str).unique()),
            default=None,
        )
        surgery_only = st.checkbox("Surgery cases only")

    filtered = ipd[ipd["hospital"].isin(hospitals) & ipd["month"].isin(months)].copy()
    if tpas:
        filtered = filtered[filtered["TPA"].astype(str).isin(tpas)]
    if surgery_only:
        filtered = filtered[filtered["is_surgery"]]
    return filtered


def render_kpis(ipd: pd.DataFrame) -> None:
    kpis = executive_kpis(ipd)
    cols = st.columns(6)
    cols[0].metric("Cases", f"{kpis['cases']:,.0f}")
    cols[1].metric("Surgery Cases", f"{kpis['surgery_cases']:,.0f}", format_pct(kpis["surgery_rate"]))
    cols[2].metric("Total Billing / Deposit", format_money(kpis["total_deposit"]))
    cols[3].metric("Hospital Revenue", format_money(kpis["hospital_revenue"]))
    cols[4].metric("HLR Amount", format_money(kpis["hlr_amount"]))
    cols[5].metric("Discounts", format_money(kpis["discount"]), format_pct(kpis["discount_rate"]))

    cols = st.columns(3)
    cols[0].metric("Avg LOS / BOR Days", f"{kpis['average_los']:,.1f}")
    cols[1].metric("Revenue Per Case", format_money(kpis["revenue_per_case"]))
    cols[2].metric("Non-Surgery Cases", f"{kpis['non_surgery_cases']:,.0f}")


def render_executive(ipd: pd.DataFrame) -> None:
    st.subheader("Executive Overview")
    render_kpis(ipd)
    hospital_df = by_hospital(ipd)
    if hospital_df.empty:
        st.info("No IPD data loaded.")
        return

    left, right = st.columns(2)
    with left:
        fig = px.bar(
            hospital_df,
            x="hospital",
            y=["cases", "surgeries"],
            barmode="group",
            title="Cases and Surgery Cases by Hospital",
        )
        st.plotly_chart(fig, width="stretch")
    with right:
        fig = px.bar(
            hospital_df,
            x="hospital",
            y="hospital_revenue",
            color="hospital",
            title="Hospital Revenue by Hospital",
        )
        st.plotly_chart(fig, width="stretch")

    display = hospital_df.copy()
    for col in ["total_deposit", "hospital_revenue", "hlr_amount", "discount", "revenue_per_case"]:
        display[col] = display[col].map(format_money)
    for col in ["surgery_rate", "discount_rate"]:
        display[col] = display[col].map(format_pct)
    st.dataframe(display, width="stretch", hide_index=True)


def render_monthly(ipd: pd.DataFrame) -> None:
    st.subheader("Monthly Trends")
    trend = monthly(ipd)
    if trend.empty:
        st.info("No monthly trend data available.")
        return
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            px.line(trend, x="month", y="cases", color="hospital", markers=True, title="Cases by Month"),
            width="stretch",
        )
    with right:
        st.plotly_chart(
            px.line(
                trend,
                x="month",
                y="hospital_revenue",
                color="hospital",
                markers=True,
                title="Hospital Revenue by Month",
            ),
            width="stretch",
        )
    st.plotly_chart(
        px.bar(
            trend,
            x="month",
            y=["surgeries", "cash_cases"],
            color="hospital",
            barmode="group",
            title="Surgeries and Cash Cases",
        ),
        width="stretch",
    )


def render_revenue(ipd: pd.DataFrame) -> None:
    st.subheader("Revenue and Cost Mix")
    mix = cost_mix(ipd)
    if mix.empty:
        st.info("No revenue mix data available.")
        return
    left, right = st.columns([1, 1])
    with left:
        st.plotly_chart(px.pie(mix, values="amount", names="component", title="Financial Component Mix"), width="stretch")
    with right:
        st.plotly_chart(px.bar(mix, x="component", y="amount", title="Component Amounts"), width="stretch")


def render_marketing(ipd: pd.DataFrame) -> None:
    st.subheader("Marketing and Referral Performance")
    dimensions = {
        "Marketing Code": "Mkg",
        "Referral": "REF",
        "Consultant": "Con 1",
        "Specialty": "Spl",
        "TPA / Cash": "TPA",
        "Case Type": "Type",
    }
    selected = st.selectbox("Segment by", list(dimensions.keys()))
    ranked = ranked_dimension(ipd, dimensions[selected])
    if ranked.empty:
        st.info("No segment data available.")
        return
    st.plotly_chart(
        px.bar(
            ranked,
            x="segment",
            y="hospital_revenue",
            color="cases",
            title=f"Top {selected} Segments by Hospital Revenue",
        ),
        width="stretch",
    )
    st.dataframe(ranked, width="stretch", hide_index=True)


def render_doctors(doctor_targets: pd.DataFrame, other_business: pd.DataFrame) -> None:
    st.subheader("Doctor and Business Performance")
    tabs = st.tabs(["Doctor Targets", "Other Business"])
    with tabs[0]:
        ach = target_achievement(doctor_targets)
        if ach.empty:
            st.info("No doctor target table parsed.")
        else:
            selected_months = st.multiselect(
                "Doctor target months",
                list(ach.sort_values("month_order")["month"].unique()),
                default=list(ach.sort_values("month_order")["month"].unique()),
            )
            view = ach[ach["month"].isin(selected_months)]
            st.plotly_chart(
                px.bar(
                    view.groupby("entity", as_index=False)[["target", "actual"]].sum().sort_values("actual", ascending=False),
                    x="entity",
                    y=["target", "actual"],
                    barmode="group",
                    title="Doctor Target vs Actual",
                ),
                width="stretch",
            )
            st.dataframe(view, width="stretch", hide_index=True)
    with tabs[1]:
        ach = target_achievement(other_business)
        if ach.empty:
            st.info("No other business target table parsed.")
        else:
            st.plotly_chart(
                px.bar(
                    ach.groupby(["entity", "category"], as_index=False)[["target", "actual"]].sum(),
                    x="category",
                    y=["target", "actual"],
                    color="entity",
                    barmode="group",
                    title="Other Business Target vs Actual",
                ),
                width="stretch",
            )
            st.dataframe(ach, width="stretch", hide_index=True)


def render_operations(meeting_actions: pd.DataFrame) -> None:
    st.subheader("Operations")
    if meeting_actions.empty:
        st.info("No core team meeting actions parsed.")
        return
    owners = st.multiselect(
        "Owners",
        sorted(meeting_actions["owner"].dropna().unique()),
        default=sorted(meeting_actions["owner"].dropna().unique()),
    )
    st.dataframe(meeting_actions[meeting_actions["owner"].isin(owners)], width="stretch", hide_index=True)


def render_quality(data: Any, ipd: pd.DataFrame) -> None:
    st.subheader("Data Quality")
    if data.warnings:
        for warning in data.warnings:
            st.warning(warning)
    st.markdown("#### Tab Audit")
    st.dataframe(data.tab_audit, width="stretch", hide_index=True)

    quality_cols = st.columns(3)
    duplicate_df = duplicate_patients(ipd)
    quality_cols[0].metric("Duplicate patient rows", f"{len(duplicate_df):,.0f}")
    quality_cols[1].metric("Unknown month rows", f"{int(ipd['month'].eq('UNKNOWN').sum()) if not ipd.empty else 0:,.0f}")
    quality_cols[2].metric("Rows loaded", f"{len(ipd):,.0f}")
    if not duplicate_df.empty:
        st.markdown("#### Duplicate Patient Candidates")
        st.dataframe(duplicate_df, width="stretch", hide_index=True)


def main() -> None:
    authenticate()
    st.title(APP_TITLE)
    st.caption("Executive BI for IPD, hospital revenue, doctor targets, and operational follow-ups.")

    defaults = default_sources()
    with st.sidebar:
        st.header("Data Sources")
        auto_refresh = st.checkbox("Auto-refresh dashboard", value=True)
        refresh_minutes = st.number_input("Auto-refresh interval, minutes", min_value=1, max_value=60, value=5)
        manual_refresh = st.button("Refresh now", width="stretch")
        st.caption(f"Last screen refresh: {datetime.now():%d %b %Y, %H:%M:%S}")

        if "refresh_token" not in st.session_state:
            st.session_state.refresh_token = 0
        if manual_refresh:
            st.session_state.refresh_token += 1
            st.cache_data.clear()

        balajee = load_source_from_controls("Balajee", defaults["Balajee"])
        sbs = load_source_from_controls("SBS Andheri", defaults["SBS Andheri"])
        doctors = load_source_from_controls("Doctors", defaults["Doctors"])

        st.divider()
        st.caption(
            "When using public Google Sheets, the app downloads the XLSX export each refresh. "
            f"Auto-refresh reloads the dashboard every {refresh_minutes} minutes while this page is open."
        )
        install_auto_refresh(auto_refresh, refresh_minutes)

    data = cached_dashboard_data(
        balajee.name if balajee else None,
        balajee.content if balajee else None,
        sbs.name if sbs else None,
        sbs.content if sbs else None,
        doctors.name if doctors else None,
        doctors.content if doctors else None,
        st.session_state.refresh_token,
    )

    with st.expander("Source Status", expanded=True):
        render_source_status(
            data,
            {"Balajee": balajee, "SBS Andheri": sbs, "Doctors": doctors},
        )

    ipd = apply_filters(data.ipd_cases)
    pages = st.tabs(
        [
            "Executive Overview",
            "Monthly Trends",
            "Revenue Mix",
            "Marketing & Referral",
            "Doctor Performance",
            "Operations",
            "Data Quality",
        ]
    )
    with pages[0]:
        render_executive(ipd)
    with pages[1]:
        render_monthly(ipd)
    with pages[2]:
        render_revenue(ipd)
    with pages[3]:
        render_marketing(ipd)
    with pages[4]:
        render_doctors(data.doctor_targets, data.other_business_targets)
    with pages[5]:
        render_operations(data.meeting_actions)
    with pages[6]:
        render_quality(data, ipd)


if __name__ == "__main__":
    main()
