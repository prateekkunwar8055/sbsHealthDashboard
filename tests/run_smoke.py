import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_parsing_smoke import test_google_sheet_export_url, test_local_workbooks_parse_when_available


if __name__ == "__main__":
    test_google_sheet_export_url()
    test_local_workbooks_parse_when_available()
    print("Smoke checks passed.")
