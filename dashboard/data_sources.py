"""Input handling for local Excel workbooks and public Google Sheet links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import re
from typing import BinaryIO

try:
    import requests
except ImportError:  # pragma: no cover - handled when Google Sheet mode is used
    requests = None


GOOGLE_SHEET_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)")


@dataclass(frozen=True)
class WorkbookSource:
    name: str
    content: bytes
    loaded_at: datetime
    source_type: str


def google_sheet_export_url(url: str) -> str:
    """Return an XLSX export URL for a public Google Sheets URL."""
    match = GOOGLE_SHEET_RE.search(url or "")
    if not match:
        raise ValueError("Enter a valid Google Sheets URL containing /spreadsheets/d/<sheet-id>.")
    sheet_id = match.group(1)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"


def download_google_sheet(url: str, name: str, timeout: int = 45) -> WorkbookSource:
    if requests is None:
        raise RuntimeError("Install the 'requests' package to load public Google Sheet links.")
    export_url = google_sheet_export_url(url)
    response = requests.get(export_url, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" in content_type.lower():
        raise ValueError(
            f"{name} returned an HTML page. Confirm the Google Sheet is publicly shared."
        )
    return WorkbookSource(
        name=name,
        content=response.content,
        loaded_at=datetime.now(),
        source_type="google_sheet",
    )


def uploaded_workbook(file: BinaryIO, name: str | None = None) -> WorkbookSource:
    content = file.read()
    return WorkbookSource(
        name=name or getattr(file, "name", "Uploaded workbook"),
        content=content,
        loaded_at=datetime.now(),
        source_type="upload",
    )


def local_workbook(path: str, name: str | None = None) -> WorkbookSource:
    with open(path, "rb") as handle:
        content = handle.read()
    return WorkbookSource(
        name=name or path,
        content=content,
        loaded_at=datetime.now(),
        source_type="local_file",
    )


def as_excel_buffer(source: WorkbookSource) -> BytesIO:
    return BytesIO(source.content)
