from pathlib import Path

from dashboard.data_sources import google_sheet_export_url, local_workbook
from dashboard.parsing import build_dashboard_data


def test_google_sheet_export_url():
    url = "https://docs.google.com/spreadsheets/d/abc-123_XYZ/edit#gid=0"
    assert google_sheet_export_url(url) == "https://docs.google.com/spreadsheets/d/abc-123_XYZ/export?format=xlsx"


def test_local_workbooks_parse_when_available():
    downloads = Path.home() / "Downloads"
    paths = {
        "balajee": downloads / "IPD Balajee .xlsx",
        "sbs": downloads / "IPD SBS Andheri.xlsx",
        "doctors": downloads / "DOCTORS LIST.xlsx",
    }
    if not all(path.exists() for path in paths.values()):
        return

    balajee = local_workbook(str(paths["balajee"]), "IPD Balajee .xlsx")
    sbs = local_workbook(str(paths["sbs"]), "IPD SBS Andheri.xlsx")
    doctors = local_workbook(str(paths["doctors"]), "DOCTORS LIST.xlsx")
    data = build_dashboard_data(
        (balajee.name, balajee.content),
        (sbs.name, sbs.content),
        (doctors.name, doctors.content),
    )

    assert not data.ipd_cases.empty
    assert {"Balajee", "SBS Andheri"} <= set(data.ipd_cases["hospital"].unique())
    assert len(data.tab_audit) >= 20
    assert not data.meeting_actions.empty
