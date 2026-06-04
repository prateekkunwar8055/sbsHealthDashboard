"""Workbook parsers and normalizers for the hospital BI dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

import pandas as pd


IPD_SHEET = "IPD 26-27"
IPD_HEADER_ROW = 2
PATIENT_COL = "PATIENT'S NAME"

AMOUNT_COLUMNS = [
    "Deposit",
    "Approval",
    "Tot AmtDeposit",
    "Lab",
    "Radio",
    "Medicine",
    "Implants",
    "HLR Amt",
    "Hosp",
    "1H",
    "1L",
    "1R",
    "1C",
    "2H",
    "2L",
    "2R",
    "2M",
    "2C",
    "Anaes Amount",
    "Assistant Amount",
    "Other Assistant Amount",
    "Others",
    "L Exp",
    "R Exp",
    "Hospital",
    "Discount",
]

MONTH_ORDER = {
    "APR": 1,
    "MAY": 2,
    "JUN": 3,
    "JUL": 4,
    "AUG": 5,
    "SEP": 6,
    "OCT": 7,
    "NOV": 8,
    "DEC": 9,
    "JAN": 10,
    "FEB": 11,
    "MAR": 12,
}


@dataclass
class ParsedWorkbook:
    name: str
    tabs: list[dict[str, Any]]
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DashboardData:
    ipd_cases: pd.DataFrame
    hospital_reference: dict[str, dict[str, pd.DataFrame]]
    doctor_targets: pd.DataFrame
    other_business_targets: pd.DataFrame
    doctor_detail_tabs: dict[str, pd.DataFrame]
    meeting_actions: pd.DataFrame
    tab_audit: pd.DataFrame
    warnings: list[str]


def _clean_header(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _dedupe_columns(columns: list[Any]) -> list[str]:
    counts: dict[str, int] = {}
    cleaned: list[str] = []
    for raw in columns:
        base = _clean_header(raw) or "Unnamed"
        counts[base] = counts.get(base, 0) + 1
        cleaned.append(base if counts[base] == 1 else f"{base} {counts[base]}")
    return cleaned


def _read_excel(buffer: BytesIO) -> pd.ExcelFile:
    buffer.seek(0)
    return pd.ExcelFile(buffer, engine="openpyxl")


def _tab_audit(excel: pd.ExcelFile) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    tabs: list[dict[str, Any]] = []
    raw_tables: dict[str, pd.DataFrame] = {}
    for sheet_name in excel.sheet_names:
        df = pd.read_excel(excel, sheet_name=sheet_name, header=None, dtype=object)
        raw_tables[sheet_name] = df
        non_empty = df.dropna(how="all").dropna(axis=1, how="all")
        tabs.append(
            {
                "sheet": sheet_name,
                "rows": int(non_empty.shape[0]),
                "columns": int(non_empty.shape[1]),
                "non_empty_cells": int(df.notna().sum().sum()),
                "empty": bool(non_empty.empty),
            }
        )
    return tabs, raw_tables


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _month_label(value: Any) -> str:
    text = str(value or "").upper().strip().replace("'", "")
    for month in MONTH_ORDER:
        if text.startswith(month):
            return month
    return "UNKNOWN"


def parse_ipd_workbook(name: str, content: bytes, hospital: str) -> ParsedWorkbook:
    excel = _read_excel(BytesIO(content))
    tabs, raw_tables = _tab_audit(excel)
    parsed = ParsedWorkbook(name=name, tabs=tabs, tables={}, warnings=[])

    if IPD_SHEET not in excel.sheet_names:
        parsed.warnings.append(f"{hospital}: missing required sheet '{IPD_SHEET}'.")
        return parsed

    df = pd.read_excel(excel, sheet_name=IPD_SHEET, header=IPD_HEADER_ROW, dtype=object)
    df.columns = _dedupe_columns(list(df.columns))
    if PATIENT_COL not in df.columns:
        parsed.warnings.append(f"{hospital}: patient column not found in '{IPD_SHEET}'.")
        return parsed

    before = len(df)
    df = df[df[PATIENT_COL].notna()].copy()
    df = df[df[PATIENT_COL].astype(str).str.strip() != ""].copy()
    excluded = before - len(df)
    if excluded:
        parsed.warnings.append(f"{hospital}: excluded {excluded} blank/non-patient rows from IPD data.")

    df["hospital"] = hospital
    df["patient_name"] = df[PATIENT_COL].astype(str).str.strip()
    df["month"] = df.get("D-Mon", df.get("Mon", "")).map(_month_label)
    df["month_order"] = df["month"].map(MONTH_ORDER).fillna(99).astype(int)
    df["is_surgery"] = (
        df.get("Sur", "")
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .replace({"0": "", "NO": "", "N": "", "NONE": "", "NAN": ""})
        != ""
    )
    df["los_days"] = _numeric(df.get("BOR", pd.Series(index=df.index, dtype=object)))

    amount_renames = {
        "Amount": "Anaes Amount",
        "Amount 2": "Assistant Amount",
        "Amount 3": "Other Assistant Amount",
    }
    df = df.rename(columns=amount_renames)
    for column in AMOUNT_COLUMNS:
        if column in df.columns:
            df[column] = _numeric(df[column])

    parsed.tables["ipd_cases"] = df
    for sheet_name, raw in raw_tables.items():
        if sheet_name != IPD_SHEET and not raw.dropna(how="all").dropna(axis=1, how="all").empty:
            parsed.tables[sheet_name] = raw
    return parsed


def parse_doctors_workbook(name: str, content: bytes) -> ParsedWorkbook:
    excel = _read_excel(BytesIO(content))
    tabs, raw_tables = _tab_audit(excel)
    parsed = ParsedWorkbook(name=name, tabs=tabs, tables={}, warnings=[])

    if "Compiled" in raw_tables:
        parsed.tables["doctor_targets"] = _parse_monthly_target_table(raw_tables["Compiled"], "doctor")
    else:
        parsed.warnings.append("Doctors workbook: missing 'Compiled' sheet.")

    if "Other Business" in raw_tables:
        parsed.tables["other_business_targets"] = _parse_monthly_target_table(
            raw_tables["Other Business"], "business"
        )
    else:
        parsed.warnings.append("Doctors workbook: missing 'Other Business' sheet.")

    if "Core Team Meeting" in raw_tables:
        parsed.tables["meeting_actions"] = _parse_meeting_actions(raw_tables["Core Team Meeting"])

    detail_tabs: dict[str, pd.DataFrame] = {}
    for sheet_name, raw in raw_tables.items():
        if sheet_name not in {"Compiled", "Other Business", "Core Team Meeting"}:
            compact = raw.dropna(how="all").dropna(axis=1, how="all")
            if not compact.empty:
                detail_tabs[sheet_name] = compact
    parsed.tables["doctor_detail_tabs"] = detail_tabs  # type: ignore[assignment]
    return parsed


def _parse_monthly_target_table(raw: pd.DataFrame, table_type: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if raw.empty:
        return pd.DataFrame()

    month_row = raw.iloc[2] if len(raw) > 2 else pd.Series(dtype=object)
    month_columns = {
        col: _month_label(value)
        for col, value in month_row.items()
        if _month_label(value) != "UNKNOWN"
    }
    if not month_columns:
        return pd.DataFrame()

    performance_start = min([c for c in month_columns if c >= 17], default=None)
    target_month_cols = {c: m for c, m in month_columns.items() if performance_start is None or c < performance_start}
    actual_month_cols = {c: m for c, m in month_columns.items() if performance_start is not None and c >= performance_start}

    for row_idx in range(3, len(raw)):
        row = raw.iloc[row_idx]
        if table_type == "doctor":
            entity = row.get(1)
            category = "Doctor"
            annual_target = row.get(2)
        else:
            entity = row.get(1)
            category = row.get(2)
            annual_target = row.get(3)
        if pd.isna(entity) or str(entity).strip() == "":
            continue
        for col, month in target_month_cols.items():
            rows.append(
                {
                    "entity": str(entity).strip(),
                    "category": str(category).strip() if not pd.isna(category) else "",
                    "month": month,
                    "month_order": MONTH_ORDER.get(month, 99),
                    "target": pd.to_numeric(row.get(col), errors="coerce"),
                    "actual": pd.NA,
                    "annual_target": pd.to_numeric(annual_target, errors="coerce"),
                    "table_type": table_type,
                }
            )
        for col, month in actual_month_cols.items():
            rows.append(
                {
                    "entity": str(entity).strip(),
                    "category": str(category).strip() if not pd.isna(category) else "",
                    "month": month,
                    "month_order": MONTH_ORDER.get(month, 99),
                    "target": pd.NA,
                    "actual": pd.to_numeric(row.get(col), errors="coerce"),
                    "annual_target": pd.to_numeric(annual_target, errors="coerce"),
                    "table_type": table_type,
                }
            )

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return (
        out.groupby(["entity", "category", "month", "month_order", "table_type"], dropna=False)
        .agg(target=("target", "sum"), actual=("actual", "sum"), annual_target=("annual_target", "max"))
        .reset_index()
    )


def _parse_meeting_actions(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["meeting_date", "owner", "topic", "notes"])
    meeting_date = None
    date_values = raw.stack().dropna()
    if not date_values.empty:
        for value in date_values:
            parsed = pd.to_datetime(value, errors="coerce")
            if not pd.isna(parsed):
                meeting_date = parsed.date()
                break
    rows: list[dict[str, Any]] = []
    for _, row in raw.iterrows():
        owner = row.get(1)
        topic = row.get(2)
        notes = row.get(3)
        if pd.isna(owner) or pd.isna(topic):
            continue
        rows.append(
            {
                "meeting_date": meeting_date,
                "owner": str(owner).strip(),
                "topic": str(topic).strip(),
                "notes": "" if pd.isna(notes) else str(notes).strip(),
            }
        )
    return pd.DataFrame(rows)


def build_dashboard_data(
    balajee: tuple[str, bytes] | None,
    sbs: tuple[str, bytes] | None,
    doctors: tuple[str, bytes] | None,
) -> DashboardData:
    warnings: list[str] = []
    tab_rows: list[dict[str, Any]] = []
    ipd_frames: list[pd.DataFrame] = []
    hospital_reference: dict[str, dict[str, pd.DataFrame]] = {}
    doctor_targets = pd.DataFrame()
    other_business_targets = pd.DataFrame()
    doctor_detail_tabs: dict[str, pd.DataFrame] = {}
    meeting_actions = pd.DataFrame(columns=["meeting_date", "owner", "topic", "notes"])

    for source, hospital in [(balajee, "Balajee"), (sbs, "SBS Andheri")]:
        if not source:
            warnings.append(f"{hospital}: no source loaded.")
            continue
        name, content = source
        parsed = parse_ipd_workbook(name, content, hospital)
        warnings.extend(parsed.warnings)
        tab_rows.extend([{**tab, "workbook": name, "role": hospital} for tab in parsed.tabs])
        if "ipd_cases" in parsed.tables:
            ipd_frames.append(parsed.tables["ipd_cases"])
        hospital_reference[hospital] = {
            key: value for key, value in parsed.tables.items() if key != "ipd_cases"
        }

    if doctors:
        name, content = doctors
        parsed = parse_doctors_workbook(name, content)
        warnings.extend(parsed.warnings)
        tab_rows.extend([{**tab, "workbook": name, "role": "Doctors"} for tab in parsed.tabs])
        doctor_targets = parsed.tables.get("doctor_targets", pd.DataFrame())
        other_business_targets = parsed.tables.get("other_business_targets", pd.DataFrame())
        doctor_detail_tabs = parsed.tables.get("doctor_detail_tabs", {})  # type: ignore[assignment]
        meeting_actions = parsed.tables.get("meeting_actions", meeting_actions)
    else:
        warnings.append("Doctors workbook: no source loaded.")

    ipd_cases = pd.concat(ipd_frames, ignore_index=True) if ipd_frames else pd.DataFrame()
    tab_audit = pd.DataFrame(tab_rows)
    return DashboardData(
        ipd_cases=ipd_cases,
        hospital_reference=hospital_reference,
        doctor_targets=doctor_targets,
        other_business_targets=other_business_targets,
        doctor_detail_tabs=doctor_detail_tabs,
        meeting_actions=meeting_actions,
        tab_audit=tab_audit,
        warnings=warnings,
    )
