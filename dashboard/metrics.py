"""Aggregations used by the Streamlit dashboard."""

from __future__ import annotations

import pandas as pd


def money(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def executive_kpis(ipd: pd.DataFrame) -> dict[str, float]:
    if ipd.empty:
        return {
            "cases": 0,
            "surgery_cases": 0,
            "non_surgery_cases": 0,
            "total_deposit": 0,
            "hospital_revenue": 0,
            "hlr_amount": 0,
            "discount": 0,
            "average_los": 0,
            "revenue_per_case": 0,
            "surgery_rate": 0,
            "discount_rate": 0,
        }
    cases = len(ipd)
    surgeries = int(ipd.get("is_surgery", pd.Series(dtype=bool)).fillna(False).sum())
    hospital_revenue = money(ipd, "Hospital")
    total_deposit = money(ipd, "Tot AmtDeposit")
    discount = money(ipd, "Discount")
    return {
        "cases": cases,
        "surgery_cases": surgeries,
        "non_surgery_cases": cases - surgeries,
        "total_deposit": total_deposit,
        "hospital_revenue": hospital_revenue,
        "hlr_amount": money(ipd, "HLR Amt"),
        "discount": discount,
        "average_los": float(pd.to_numeric(ipd.get("los_days", 0), errors="coerce").mean() or 0),
        "revenue_per_case": hospital_revenue / cases if cases else 0,
        "surgery_rate": surgeries / cases if cases else 0,
        "discount_rate": discount / total_deposit if total_deposit else 0,
    }


def by_hospital(ipd: pd.DataFrame) -> pd.DataFrame:
    if ipd.empty:
        return pd.DataFrame()
    grouped = (
        ipd.groupby("hospital", dropna=False)
        .agg(
            cases=("patient_name", "count"),
            surgeries=("is_surgery", "sum"),
            los_days=("los_days", "mean"),
            total_deposit=("Tot AmtDeposit", "sum"),
            hospital_revenue=("Hospital", "sum"),
            hlr_amount=("HLR Amt", "sum"),
            discount=("Discount", "sum"),
        )
        .reset_index()
    )
    grouped["revenue_per_case"] = grouped["hospital_revenue"] / grouped["cases"].replace(0, pd.NA)
    grouped["surgery_rate"] = grouped["surgeries"] / grouped["cases"].replace(0, pd.NA)
    grouped["discount_rate"] = grouped["discount"] / grouped["total_deposit"].replace(0, pd.NA)
    return grouped.fillna(0)


def monthly(ipd: pd.DataFrame) -> pd.DataFrame:
    if ipd.empty:
        return pd.DataFrame()
    return (
        ipd.groupby(["month_order", "month", "hospital"], dropna=False)
        .agg(
            cases=("patient_name", "count"),
            surgeries=("is_surgery", "sum"),
            total_deposit=("Tot AmtDeposit", "sum"),
            hospital_revenue=("Hospital", "sum"),
            discounts=("Discount", "sum"),
            cash_cases=("TPA", lambda s: s.astype(str).str.upper().eq("CASH").sum()),
        )
        .reset_index()
        .sort_values(["month_order", "hospital"])
    )


def cost_mix(ipd: pd.DataFrame) -> pd.DataFrame:
    columns = ["Lab", "Radio", "Medicine", "Implants", "Hospital", "HLR Amt", "Discount", "Others"]
    rows = [{"component": col, "amount": money(ipd, col)} for col in columns]
    return pd.DataFrame(rows).query("amount != 0")


def ranked_dimension(ipd: pd.DataFrame, column: str, limit: int = 20) -> pd.DataFrame:
    if ipd.empty or column not in ipd.columns:
        return pd.DataFrame()
    return (
        ipd.groupby(column, dropna=False)
        .agg(
            cases=("patient_name", "count"),
            surgeries=("is_surgery", "sum"),
            hospital_revenue=("Hospital", "sum"),
            total_deposit=("Tot AmtDeposit", "sum"),
            discounts=("Discount", "sum"),
        )
        .reset_index()
        .rename(columns={column: "segment"})
        .sort_values("hospital_revenue", ascending=False)
        .head(limit)
    )


def target_achievement(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return pd.DataFrame()
    out = table.copy()
    out["target"] = pd.to_numeric(out.get("target"), errors="coerce").fillna(0)
    out["actual"] = pd.to_numeric(out.get("actual"), errors="coerce").fillna(0)
    out["achievement"] = out["actual"] / out["target"].replace(0, pd.NA)
    return out.fillna(0)


def duplicate_patients(ipd: pd.DataFrame) -> pd.DataFrame:
    if ipd.empty:
        return pd.DataFrame()
    keys = [col for col in ["hospital", "patient_name", "YIPD", "CIPD"] if col in ipd.columns]
    if not keys:
        return pd.DataFrame()
    dupes = ipd[ipd.duplicated(keys, keep=False)]
    return dupes[keys + [col for col in ["month", "Tot AmtDeposit", "Hospital"] if col in ipd.columns]]
