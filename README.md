# Hospital BI Dashboard

Streamlit BI dashboard for the three hospital workbooks:

- `IPD Balajee .xlsx`
- `IPD SBS Andheri.xlsx`
- `DOCTORS LIST.xlsx`

The app can read the current local XLSX files from `Downloads`, uploaded XLSX files, or public Google Sheet links. Google Sheet links are converted to XLSX export URLs and re-read on manual or automatic refresh.

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
streamlit run app.py
```

### Optional login credentials

The app now requires a username and password. When deployed to Streamlit Community Cloud, add these values under **Secrets**:

```toml
[auth]
user = "your_username"
pass = "your_password"
```

If no Streamlit secret is configured, the local fallback credentials are `admin` / `admin`.

The default local-file mode expects:

```text
C:\Users\prate\Downloads\IPD Balajee .xlsx
C:\Users\prate\Downloads\IPD SBS Andheri.xlsx
C:\Users\prate\Downloads\DOCTORS LIST.xlsx
```

## Google Sheet Links

For live refresh, share each source Google Sheet publicly and paste its normal edit URL into the sidebar. Keep `Auto-refresh dashboard` enabled in the sidebar; the page reloads on the selected interval and downloads fresh XLSX exports from the three Sheet links. The app extracts the sheet ID from:

```text
https://docs.google.com/spreadsheets/d/<sheet-id>/edit...
```

and downloads:

```text
https://docs.google.com/spreadsheets/d/<sheet-id>/export?format=xlsx
```

## Dashboard Areas

- Executive overview
- Monthly trends
- Revenue and cost mix
- Marketing and referral performance
- Doctor and other business target achievement
- Core team meeting actions
- Data quality and tab audit
