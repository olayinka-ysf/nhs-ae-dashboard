"""
clean_data.py
-------------
Reads the raw NHS A&E files downloaded from NHS England and produces
clean, analysis-ready CSVs in data/processed/.

Two source files:
  1. Monthly-AE-Time-Series-February-2026.xls  -- national time series (Aug 2010-present)
  2. February-2026-AE-by-provider.csv          -- provider-level snapshot (Feb 2026)

Run from the project root:
    python scripts/clean_data.py
"""

import pandas as pd
import numpy as np
import os
import re

# -- Paths ------------------------------------------------------------------
ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR  = os.path.join(ROOT, "data", "raw")
PROC_DIR = os.path.join(ROOT, "data", "processed")
os.makedirs(PROC_DIR, exist_ok=True)

XLS_FILE = os.path.join(RAW_DIR, "Monthly-AE-Time-Series-February-2026.xls")
CSV_FILE = os.path.join(RAW_DIR, "February-2026-AE-by-provider.csv")


# ==========================================================================
# HELPER FUNCTIONS
# ==========================================================================

def clean_numeric(series):
    """
    Convert a series to nullable integers, handling two cases:

    Case 1 -- Already numeric (from XLS via xlrd): Excel stores numbers as
    float64. We round to remove floating-point noise then cast to Int64.

    Case 2 -- Formatted strings (from CSV): Values like '1,138,652 ' need
    comma and whitespace stripping before conversion.

    We use Int64 (capital I) rather than int64 so that NaN/missing values
    are preserved as pd.NA rather than forcing a float column.
    """
    if pd.api.types.is_numeric_dtype(series):
        # Already numeric -- just round and cast to nullable int
        return series.round(0).astype("Int64")
    else:
        # String -- strip formatting then parse
        return (
            series
            .astype(str)
            .str.replace(",", "", regex=False)   # remove thousands commas
            .str.strip()                          # remove whitespace
            .replace("", np.nan)                  # empty string -> NaN
            .replace("nan", np.nan)
            .replace("-", np.nan)                 # NHS dash = not applicable
            .pipe(pd.to_numeric, errors="coerce") # parse; unparseable -> NaN
            .round(0)
            .astype("Int64")                      # nullable integer type
        )


def snake_case(col):
    """
    Convert a column name to clean snake_case.

    'A&E attendances Type 1' -> 'ae_attendances_type_1'

    Steps:
      1. Lowercase everything
      2. Replace '&' with 'and'
      3. Replace any non-alphanumeric character with '_'
      4. Collapse multiple underscores into one
      5. Strip leading/trailing underscores
    """
    col = col.lower()
    col = col.replace("&", "and")
    col = re.sub(r"[^a-z0-9]+", "_", col)
    col = re.sub(r"_+", "_", col)
    col = col.strip("_")
    return col


# ==========================================================================
# FILE 1: NATIONAL TIME SERIES -- ACTIVITY SHEET
# ==========================================================================

print("=" * 60)
print("Processing: Monthly A&E Time Series -- Activity sheet")
print("=" * 60)

# WHY header=13, usecols="B:J":
#   The XLS file has 13 rows of metadata before the column headers.
#   Row 14 (0-indexed row 13 -> header=13 in pandas) contains column names.
#   Column A is blank; data runs from column B onward.
#   We use xlrd engine because this is the old .xls binary format (not .xlsx).
df_activity = pd.read_excel(
    XLS_FILE,
    sheet_name="Activity",
    header=13,       # row 14 in Excel = index 13 in pandas (0-based)
    usecols="B:J",   # skip blank column A; columns B through J cover all data
    engine="xlrd"
)

# Drop completely empty rows -- the sheet has trailing blank rows
df_activity = df_activity.dropna(how="all")

print("Rows loaded (before cleaning): {}".format(len(df_activity)))
print("Columns: {}".format(list(df_activity.columns)))

# -- Rename columns --------------------------------------------------------
# Original names are very long. We shorten to something SQL-friendly while
# keeping the meaning clear.
activity_rename = {
    "Period":                                           "period",
    "Type 1 Departments - Major A&E":                   "type1_attendances",
    "Type 2 Departments - Single Specialty":             "type2_attendances",
    "Type 3 Departments - Other A&E/Minor Injury Unit":  "type3_attendances",
    "Total Attendances":                                "total_attendances",
    "Emergency Admissions via Type 1 A&E":              "emerg_admissions_type1",
    "Emergency Admissions via Type 2 A&E":              "emerg_admissions_type2",
    "Emergency Admissions via Type 3 and 4 A&E":        "emerg_admissions_type3",
    "Total Emergency Admissions via A&E":               "total_emerg_admissions",
}
df_activity = df_activity.rename(columns=activity_rename)

# -- Parse the period column -----------------------------------------------
# Values look like 'Aug-10', 'Jan-11', etc.
# pd.to_datetime handles this with format="%b-%y".
# WHY convert to datetime? So we can filter by date range, sort chronologically,
# and extract year/month components for SQL and visualisations.
df_activity["period"] = pd.to_datetime(df_activity["period"], format="%b-%y")

# -- Clean numeric columns -------------------------------------------------
numeric_cols = [c for c in df_activity.columns if c != "period"]
for col in numeric_cols:
    df_activity[col] = clean_numeric(df_activity[col])

# -- Sort chronologically --------------------------------------------------
df_activity = df_activity.sort_values("period").reset_index(drop=True)

print("\nDate range: {} -> {}".format(
    df_activity["period"].min().strftime("%b %Y"),
    df_activity["period"].max().strftime("%b %Y")
))
print("Rows after cleaning: {}".format(len(df_activity)))
print("\nSample rows:")
print(df_activity.head(3).to_string())
print("\nNull counts:")
print(df_activity.isnull().sum().to_string())


# ==========================================================================
# FILE 1: NATIONAL TIME SERIES -- PERFORMANCE SHEET
# ==========================================================================

print("\n" + "=" * 60)
print("Processing: Monthly A&E Time Series -- Performance sheet")
print("=" * 60)

df_perf = pd.read_excel(
    XLS_FILE,
    sheet_name="Performance",
    header=13,
    usecols="B:K",   # Period + 4 within-4hrs cols + 4 over-4hrs cols + totals
    engine="xlrd"
)

df_perf = df_perf.dropna(how="all")
print("Rows loaded: {}".format(len(df_perf)))
print("Columns: {}".format(list(df_perf.columns)))

# -- Rename columns --------------------------------------------------------
# The sheet has two header rows (row 13 = group header, row 14 = sub-labels).
# pandas reads only row 14, so duplicate column names get a .1 suffix appended.
perf_rename = {
    "Period":                                                  "period",
    "Type 1 Departments - Major A&E":                          "type1_within_4hrs",
    "Type 2 Departments - Single Specialty":                   "type2_within_4hrs",
    "Type 3 Departments - Other A&E/Minor Injury Unit":        "type3_within_4hrs",
    "Total Attendances < 4 hours":                             "total_within_4hrs",
    "Type 1 Departments - Major A&E.1":                        "type1_over_4hrs",
    "Type 2 Departments - Single Specialty.1":                 "type2_over_4hrs",
    "Type 3 Departments - Other A&E/Minor Injury Unit.1":      "type3_over_4hrs",
    "Total Attendances > 4 hours":                             "total_over_4hrs",
}

df_perf = df_perf.rename(columns=perf_rename)
keep_cols = [c for c in df_perf.columns if c in perf_rename.values()]
df_perf = df_perf[keep_cols]

df_perf["period"] = pd.to_datetime(df_perf["period"], format="%b-%y")

numeric_cols = [c for c in df_perf.columns if c != "period"]
for col in numeric_cols:
    df_perf[col] = clean_numeric(df_perf[col])

# -- Derive the 4-hour performance percentage ------------------------------
# WHY calculate it here rather than only in SQL?
# Having it pre-calculated in the processed CSV makes EDA quicker.
# We also calculate it in SQL (Step 5) to demonstrate SQL skills.
# Formula: % seen within 4hrs = within_4hrs / (within_4hrs + over_4hrs) * 100
df_perf["total_all"] = df_perf["total_within_4hrs"] + df_perf["total_over_4hrs"]
df_perf["pct_within_4hrs"] = (
    df_perf["total_within_4hrs"] / df_perf["total_all"] * 100
).round(1)

df_perf = df_perf.sort_values("period").reset_index(drop=True)

print("\nDate range: {} -> {}".format(
    df_perf["period"].min().strftime("%b %Y"),
    df_perf["period"].max().strftime("%b %Y")
))
print("Rows after cleaning: {}".format(len(df_perf)))
print("\n4-hour performance range: {}% -- {}%".format(
    df_perf["pct_within_4hrs"].min(),
    df_perf["pct_within_4hrs"].max()
))
print("Most recent month: {} -> {}%".format(
    df_perf.iloc[-1]["period"].strftime("%b %Y"),
    df_perf.iloc[-1]["pct_within_4hrs"]
))


# ==========================================================================
# FILE 2: PROVIDER-LEVEL CSV -- FEBRUARY 2026
# ==========================================================================

print("\n" + "=" * 60)
print("Processing: February 2026 -- Provider-level CSV")
print("=" * 60)

df_provider = pd.read_csv(CSV_FILE)
print("Rows loaded: {}".format(len(df_provider)))
print("Columns: {}".format(list(df_provider.columns)))

# -- Rename columns to snake_case ------------------------------------------
# WHY rename? Column names like 'A&E attendances Type 1' contain spaces and
# special characters -- these require quoting in SQL and are error-prone in
# Python. snake_case names work in both without escaping.
df_provider.columns = [snake_case(c) for c in df_provider.columns]
print("\nRenamed columns: {}".format(list(df_provider.columns)))

# -- Clean the period column -----------------------------------------------
# Values look like 'MSitAE-FEBRUARY-2026'. We extract just the date portion.
# WHY: The 'MSitAE-' prefix is a collection system identifier, not useful for
# analysis.
df_provider["period"] = (
    df_provider["period"]
    .str.replace("MSitAE-", "", regex=False)   # remove collection prefix
    .str.title()                                # 'FEBRUARY-2026' -> 'February-2026'
)
df_provider["period"] = pd.to_datetime(df_provider["period"], format="%B-%Y")

# -- Clean numeric columns -------------------------------------------------
# All columns after the 4 text columns should be integers. They may be read
# as strings if any cell contained a dash '-' (NHS convention for "not
# applicable").
text_cols = {"period", "org_code", "parent_org", "org_name"}
numeric_cols = [c for c in df_provider.columns if c not in text_cols]

for col in numeric_cols:
    df_provider[col] = df_provider[col].replace("-", np.nan)
    df_provider[col] = clean_numeric(df_provider[col])

# -- Derive total Type 1 attendances (booked + non-booked) -----------------
# The 4-hour target applies to all Type 1 attendances including booked.
# WHY add these? For performance calculations we need the total denominator.
df_provider["type1_total_attendances"] = (
    df_provider["aande_attendances_type_1"].fillna(0) +
    df_provider["aande_attendances_booked_appointments_type_1"].fillna(0)
).astype("Int64")

df_provider["type1_total_over_4hrs"] = (
    df_provider["attendances_over_4hrs_type_1"].fillna(0) +
    df_provider["attendances_over_4hrs_booked_appointments_type_1"].fillna(0)
).astype("Int64")

# -- Calculate provider-level 4-hour performance ---------------------------
df_provider["type1_pct_within_4hrs"] = (
    (df_provider["type1_total_attendances"] - df_provider["type1_total_over_4hrs"])
    / df_provider["type1_total_attendances"] * 100
).round(1)

# Providers with zero Type 1 attendances -> NaN (avoid division by zero)
mask_zero = df_provider["type1_total_attendances"] == 0
df_provider.loc[mask_zero, "type1_pct_within_4hrs"] = np.nan

print("\nNull counts per column:")
print(df_provider.isnull().sum().to_string())

# -- Filter to providers with Type 1 A&E activity --------------------------
# WHY filter? Walk-in centres and single-specialty units are not subject to
# the 4-hour target. For trust-level performance analysis the Type 1
# providers are the relevant comparison group.
# We keep ALL providers in the main cleaned file AND create a Type 1 subset.
df_provider_type1 = df_provider[
    df_provider["type1_total_attendances"] > 0
].copy().reset_index(drop=True)

print("\nAll providers: {}".format(len(df_provider)))
print("Type 1 providers (subject to 4-hour target): {}".format(len(df_provider_type1)))

if len(df_provider_type1) > 0:
    print("\nType 1 performance range: {}% -- {}%".format(
        df_provider_type1["type1_pct_within_4hrs"].min(),
        df_provider_type1["type1_pct_within_4hrs"].max()
    ))
    print("Mean 4-hour performance: {:.1f}%".format(
        df_provider_type1["type1_pct_within_4hrs"].mean()
    ))


# ==========================================================================
# SAVE CLEANED FILES
# ==========================================================================

print("\n" + "=" * 60)
print("Saving cleaned files to data/processed/")
print("=" * 60)

# Save with period formatted as YYYY-MM-DD for SQL compatibility
df_activity["period"] = df_activity["period"].dt.strftime("%Y-%m-%d")
df_perf["period"] = df_perf["period"].dt.strftime("%Y-%m-%d")
df_provider["period"] = df_provider["period"].dt.strftime("%Y-%m-%d")
df_provider_type1["period"] = df_provider_type1["period"].dt.strftime("%Y-%m-%d")

out_activity = os.path.join(PROC_DIR, "ae_timeseries_activity.csv")
out_perf     = os.path.join(PROC_DIR, "ae_timeseries_performance.csv")
out_provider = os.path.join(PROC_DIR, "ae_provider_feb2026.csv")
out_type1    = os.path.join(PROC_DIR, "ae_provider_type1_feb2026.csv")

df_activity.to_csv(out_activity, index=False)
df_perf.to_csv(out_perf, index=False)
df_provider.to_csv(out_provider, index=False)
df_provider_type1.to_csv(out_type1, index=False)

print("  ae_timeseries_activity.csv     -> {} rows".format(len(df_activity)))
print("  ae_timeseries_performance.csv  -> {} rows".format(len(df_perf)))
print("  ae_provider_feb2026.csv        -> {} rows".format(len(df_provider)))
print("  ae_provider_type1_feb2026.csv  -> {} rows".format(len(df_provider_type1)))
print("\nData cleaning complete.")
