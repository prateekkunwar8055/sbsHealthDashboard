# Hospital BI Dashboard Calculations

This document explains how the dashboard calculates numbers, which workbook sheets are used, and which fields are mapped from source tabs.

## Data Sources

The app reads three workbook sources:

- `IPD Balajee .xlsx` → parsed as Balajee IPD data
- `IPD SBS Andheri.xlsx` → parsed as SBS Andheri IPD data
- `DOCTORS LIST.xlsx` → parsed as doctor and business target data

The app accepts:

- default local XLSX files from `Downloads`
- uploaded XLSX files
- public Google Sheet links

The core data pipeline is:

1. load workbooks
2. parse IPD rows from Balajee/SBS workbooks
3. parse target and meeting tables from Doctors workbook
4. aggregate metrics for dashboard charts and KPIs

## IPD workbook parsing

The two hospital workbooks are parsed by `dashboard/parsing.py` using:

- sheet name: `IPD 26-27`
- header row: row index 2 in the sheet (`header=2` in pandas)
- required patient column: `PATIENT'S NAME`

### Row filtering

Rows are kept only when `PATIENT'S NAME` is present and not blank.

### Added normalized fields

The parser adds these normalized fields to each IPD row:

- `hospital` = source role name (`Balajee` or `SBS Andheri`)
- `patient_name` = trimmed value of `PATIENT'S NAME`
- `month` = parsed from `D-Mon` or `Mon`
- `month_order` = numeric order from `MONTH_ORDER`
- `is_surgery` = boolean derived from `Sur`
- `los_days` = numeric value from `BOR`

### Month parsing

The month label is extracted by reading the value from `D-Mon` or `Mon`, uppercasing it, stripping quotes, and matching against:

- `APR`, `MAY`, `JUN`, `JUL`, `AUG`, `SEP`, `OCT`, `NOV`, `DEC`, `JAN`, `FEB`, `MAR`

If no month matches, the row gets `UNKNOWN`.

### Surgery detection

The `Sur` field is treated as a surgery indicator. It is normalized by:

- trimming whitespace
- uppercasing
- ignoring values: `0`, `NO`, `N`, `NONE`, `NAN`

If any other non-empty value remains, `is_surgery` becomes `True`.

### Numeric amount normalization

The parser converts many amount columns to numeric values, defaulting missing or invalid values to `0`.

Columns normalized include:

- `Deposit`
- `Approval`
- `Tot AmtDeposit`
- `Lab`
- `Radio`
- `Medicine`
- `Implants`
- `HLR Amt`
- `Hosp`
- `1H`, `1L`, `1R`, `1C`
- `2H`, `2L`, `2R`, `2M`, `2C`
- `Anaes Amount`
- `Assistant Amount`
- `Other Assistant Amount`
- `Others`
- `L Exp`
- `R Exp`
- `Hospital`
- `Discount`

The parser also renames columns when present:

- `Amount` → `Anaes Amount`
- `Amount 2` → `Assistant Amount`
- `Amount 3` → `Other Assistant Amount`

### Additional columns used in dashboards

These columns are used by dashboard charts and tables when available:

- `Mkg` → Marketing Code segment
- `REF` → Referral segment
- `Con 1` → Consultant segment
- `Spl` → Specialty segment
- `TPA` → TPA / Cash segment and cash case counting
- `Type` → Case Type segment
- `YIPD`, `CIPD` → duplicate patient detection keys

## Doctor workbook parsing

The Doctors workbook is parsed by `dashboard/parsing.py`.

### Expected sheets

- `Compiled` → doctor monthly targets
- `Other Business` → other business monthly targets
- `Core Team Meeting` → meeting action items

If a sheet is missing, a warning is emitted.

### Monthly target parsing

Target sheets are parsed with `_parse_monthly_target_table()`.

How it works:

- reads the third raw row (`raw.iloc[2]`) and treats it as the month header row
- identifies columns containing valid month labels
- splits columns into two sets:
  - target columns before column index 17
  - actual performance columns at or after column index 17

For each data row:

- doctor table (`table_type == 'doctor'`):
  - entity = column index 1
  - annual_target = column index 2
- other business table (`table_type == 'business'`):
  - entity = column index 1
  - category = column index 2
  - annual_target = column index 3

For each month column, the parser emits one row with:

- `entity`
- `category`
- `month`
- `month_order`
- `target` or `actual`
- `annual_target`
- `table_type`

Then it groups by `entity`, `category`, `month`, `month_order`, `table_type` and sums `target` and `actual`.

### Core Team Meeting parsing

The `Core Team Meeting` sheet is scanned for any date value in the sheet and uses the first parseable date as `meeting_date`.

The parser then reads rows and keeps entries with both:

- owner = column index 1
- topic = column index 2

The output columns are:

- `meeting_date`
- `owner`
- `topic`
- `notes`

### Doctor detail tabs

Any other non-empty sheet in the Doctors workbook is kept as a detail tab under `doctor_detail_tabs`.

## Dashboard metrics and formulas

The aggregated IPD dataset is made available as `ipd_cases` in `DashboardData`.

### Executive KPIs (`dashboard/metrics.py`) 

The executive overview uses these formulas:

- `cases` = number of rows in IPD dataset
- `surgery_cases` = sum of `is_surgery` True values
- `non_surgery_cases` = `cases - surgery_cases`
- `total_deposit` = sum of `Tot AmtDeposit`
- `hospital_revenue` = sum of `Hospital`
- `hlr_amount` = sum of `HLR Amt`
- `discount` = sum of `Discount`
- `average_los` = mean of `los_days`
- `revenue_per_case` = `hospital_revenue / cases` if `cases > 0`
- `surgery_rate` = `surgery_cases / cases` if `cases > 0`
- `discount_rate` = `discount / total_deposit` if `total_deposit > 0`

### Hospital summary by hospital

`by_hospital()` groups by `hospital` and computes:

- `cases` = count of `patient_name`
- `surgeries` = sum of `is_surgery`
- `los_days` = mean of `los_days`
- `total_deposit` = sum of `Tot AmtDeposit`
- `hospital_revenue` = sum of `Hospital`
- `hlr_amount` = sum of `HLR Amt`
- `discount` = sum of `Discount`
- `revenue_per_case` = `hospital_revenue / cases`
- `surgery_rate` = `surgeries / cases`
- `discount_rate` = `discount / total_deposit`

### Monthly trends

`monthly()` groups by `month_order`, `month`, and `hospital` and computes:

- `cases` = count of `patient_name`
- `surgeries` = sum of `is_surgery`
- `total_deposit` = sum of `Tot AmtDeposit`
- `hospital_revenue` = sum of `Hospital`
- `discounts` = sum of `Discount`
- `cash_cases` = count of rows where `TPA` equals `CASH` (case-insensitive)

### Revenue and cost mix

`cost_mix()` sums these components across all IPD rows:

- `Lab`
- `Radio`
- `Medicine`
- `Implants`
- `Hospital`
- `HLR Amt`
- `Discount`
- `Others`

The output is displayed as a pie chart and bar chart.

### Marketing and referral ranking

`ranked_dimension(ipd, column)` groups by the selected dimension column and computes:

- `cases` = count of `patient_name`
- `surgeries` = sum of `is_surgery`
- `hospital_revenue` = sum of `Hospital`
- `total_deposit` = sum of `Tot AmtDeposit`
- `discounts` = sum of `Discount`

Supported segment columns are:

- `Mkg` for Marketing Code
- `REF` for Referral
- `Con 1` for Consultant
- `Spl` for Specialty
- `TPA` for TPA / Cash
- `Type` for Case Type

### Target achievement

`target_achievement(table)` computes:

- `target` = numeric value from the parsed target table
- `actual` = numeric value from the parsed actual table
- `achievement` = `actual / target` (with 0-safe division)

Doctor and other business panels display grouped sum totals by entity and category.

### Duplicate patient detection

`duplicate_patients(ipd)` identifies rows duplicated on the first available key set among:

- `hospital`
- `patient_name`
- `YIPD`
- `CIPD`

If such duplicate rows exist, the dashboard shows them with these columns when present:

- `month`
- `Tot AmtDeposit`
- `Hospital`

## Data quality and audit

The app also builds a tab audit from every workbook sheet.

For each sheet it records:

- `sheet`
- `rows` = number of non-empty rows
- `columns` = number of non-empty columns
- `non_empty_cells`
- `empty` = whether the sheet contains no non-empty cells
- `workbook` = source workbook file name
- `role` = `Balajee`, `SBS Andheri`, or `Doctors`

Warnings are emitted when:

- required sheets are missing
- required columns are missing
- blank/non-patient rows are excluded
- a source is not loaded

## Summary of key source fields used in calculations

### IPD `IPD 26-27` sheet

- `PATIENT'S NAME` → `patient_name`
- `D-Mon` / `Mon` → `month`
- `Sur` → `is_surgery`
- `BOR` → `los_days`
- `Tot AmtDeposit` → deposit totals / `total_deposit`
- `Hospital` → hospital revenue / `hospital_revenue`
- `HLR Amt` → `hlr_amount`
- `Discount` → `discount`
- `Lab`, `Radio`, `Medicine`, `Implants`, `Others` → cost mix components
- `TPA` → TPA / cash segmentation and `cash_cases`
- `Mkg`, `REF`, `Con 1`, `Spl`, `Type` → segmentation dimensions
- `YIPD`, `CIPD` → duplicate patient detection

### Doctors workbook

- `Compiled` → doctor monthly target table
- `Other Business` → other business monthly target table
- `Core Team Meeting` → operational meeting actions

### Target table row mapping

Doctor table (`Compiled`):

- column 1: entity name
- column 2: annual target
- month columns: target values before performance section, actual values after performance section

Other business table (`Other Business`):

- column 1: entity name
- column 2: category name
- column 3: annual target
- month columns: target and actual values split by the same performance boundary

## Notes

- The app does not currently validate column names beyond the expected names above.
- Amount fields are converted to numbers with invalid or missing values treated as `0`.
- The month split logic in doctors target parsing is based on column index positions in the sheet rather than explicit header labels.
- Only rows with a non-empty patient name are included in IPD calculations.
