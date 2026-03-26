"""
build_powerbi.py
----------------
Reads the cleaned processed CSVs and produces two Power BI-ready export files:

  output/powerbi_ready_timeseries.csv  -- 187 rows, national monthly data
  output/powerbi_ready_providers.csv   -- 198 rows, provider-level snapshot

These files differ from the processed CSVs in three ways:
  1. Extra calendar columns (year, month_num, month_name, month_label) so
     Power BI can group and filter without needing DAX date extraction
  2. The two timeseries tables (activity + performance) are merged into one
     flat file so Power BI only needs to load a single table
  3. Column names and selection are trimmed to only what the dashboard needs --
     no internal processing columns, no SQL-specific naming

Run from the project root:
    python scripts/build_powerbi.py
"""

import pandas as pd
import os

# =============================================================================
# PATHS
# =============================================================================
# os.path.abspath(__file__) gives the full path to this script file.
# os.path.dirname(...) strips the filename, leaving the directory.
# Calling dirname twice moves up one level from scripts/ to the project root.
ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC_DIR = os.path.join(ROOT, "data", "processed")
OUT_DIR  = os.path.join(ROOT, "output")
os.makedirs(OUT_DIR, exist_ok=True)


# =============================================================================
# POWER BI-READY TIMESERIES
# =============================================================================
# Source: two separate processed CSVs that must be merged.
#   ae_timeseries_activity.csv    -- attendance and admission volumes
#   ae_timeseries_performance.csv -- 4-hour target counts and percentages
#
# WHY merge them? The processed data is stored in two tables because they
# represent two different data dimensions (volume vs performance). Power BI
# can join tables via relationships, but a single flat file is simpler to
# load, requires no relationship setup, and avoids any join ambiguity.
# For a two-table merge of this size (187 rows each) there is no performance
# cost to flattening.

print("=" * 60)
print("Building: powerbi_ready_timeseries.csv")
print("=" * 60)

# --- Load the two source tables ---
df_activity = pd.read_csv(
    os.path.join(PROC_DIR, "ae_timeseries_activity.csv"),
    parse_dates=["period"]
)
df_perf = pd.read_csv(
    os.path.join(PROC_DIR, "ae_timeseries_performance.csv"),
    parse_dates=["period"]
)

print("  Activity rows loaded  : {}".format(len(df_activity)))
print("  Performance rows loaded: {}".format(len(df_perf)))

# --- Merge on period using a LEFT JOIN ---
# LEFT JOIN keeps all rows from df_activity (the left table) and brings in
# matching performance columns where available. Months where performance data
# does not exist (Aug-Oct 2010 -- the first three months) will have NaN in
# all performance columns. This is correct and expected; Power BI will treat
# those as blank/null values, which is the right representation.
#
# HOW pandas merge works:
#   on="period"   -- the column to match rows on
#   how="left"    -- keep all left rows; right rows only appear if they match
#
# Alternative: how="inner" would drop the three months with no performance
# data -- wrong here because we want those months in the output.
df_ts = pd.merge(df_activity, df_perf, on="period", how="left")

print("  Merged rows           : {}".format(len(df_ts)))

# --- Add calendar breakdown columns ---
# Power BI can extract year and month from a date column using DAX, but
# pre-computing them in the source data has two advantages:
#   1. Simpler DAX -- no need to write YEAR([period]) or FORMAT([period],"MMMM")
#      in every measure or calculated column
#   2. month_name and month_label (text) are directly usable as axis labels
#      and slicer values without any formatting
#
# WHY month_num alongside month_name?
#   Power BI sorts text columns alphabetically by default. "August" would sort
#   before "February" alphabetically. By storing month_num (1-12) we can tell
#   Power BI to "Sort by column: month_num" so months display in calendar order.

df_ts["year"]       = df_ts["period"].dt.year
df_ts["month_num"]  = df_ts["period"].dt.month
df_ts["month_name"] = df_ts["period"].dt.strftime("%B")   # "August", "September"
df_ts["month_label"]= df_ts["period"].dt.strftime("%b %Y") # "Aug 2010", "Feb 2026"

# --- Rename performance columns for clarity ---
# The performance table stores the total denominator as "total_all" -- a
# generic name that is ambiguous when sitting next to total_attendances
# (a different number). Renaming it total_4hr_denominator makes the column
# self-documenting in Power BI's field list.
df_ts = df_ts.rename(columns={"total_all": "total_4hr_denominator"})

# --- Select and order output columns ---
# We keep only the columns the dashboard needs. Dropping unused columns:
#   - Reduces file size
#   - Keeps Power BI's field list clean (no confusing duplicates or internals)
#   - Makes it obvious to anyone loading the file what each column is for
#
# Column order here matches the logical flow: date context first, then
# attendance volumes, then admissions, then 4-hour performance data.
output_cols = [
    "period",
    "year",
    "month_num",
    "month_name",
    "month_label",
    "type1_attendances",
    "type2_attendances",
    "type3_attendances",
    "total_attendances",
    "emerg_admissions_type1",
    "emerg_admissions_type2",
    "emerg_admissions_type3",
    "total_emerg_admissions",
    "type1_within_4hrs",
    "type1_over_4hrs",
    "total_within_4hrs",
    "total_over_4hrs",
    "total_4hr_denominator",
    "pct_within_4hrs",
]
df_ts = df_ts[output_cols]

# --- Sort chronologically ---
df_ts = df_ts.sort_values("period").reset_index(drop=True)

# --- Format period as YYYY-MM-DD string for CSV ---
# Power BI reads ISO 8601 date strings (YYYY-MM-DD) reliably across all
# regional settings. If we left it as a pandas Timestamp the CSV would contain
# a full datetime string which Power BI may misparse depending on locale.
df_ts["period"] = df_ts["period"].dt.strftime("%Y-%m-%d")

# --- Save ---
out_ts = os.path.join(OUT_DIR, "powerbi_ready_timeseries.csv")
df_ts.to_csv(out_ts, index=False)
print("  Saved: {}".format(out_ts))
print("  Rows: {}  |  Columns: {}".format(len(df_ts), len(df_ts.columns)))
print("  Date range: {} -> {}".format(df_ts["period"].iloc[0], df_ts["period"].iloc[-1]))
print("  Months with performance data: {}".format(df_ts["pct_within_4hrs"].notna().sum()))
print("  Months without (activity only): {}".format(df_ts["pct_within_4hrs"].isna().sum()))


# =============================================================================
# POWER BI-READY PROVIDERS
# =============================================================================
# Source: ae_provider_feb2026.csv -- 198 providers, 25 columns.
#
# The processed file has very long column names (required for SQL compatibility
# without quoting). For Power BI we rename to shorter, human-readable labels
# that will appear clearly in the Fields pane and measure editor.
#
# We also drop columns that are irrelevant to the dashboard:
#   - Type 2 and Other department breakdowns of over-4hr counts (too granular)
#   - The booked/walk-in split for Type 2 and Other (not needed at provider level)
#   - Intermediate processing columns
# Keeping the file focused on the questions the dashboard actually answers.

print("\n" + "=" * 60)
print("Building: powerbi_ready_providers.csv")
print("=" * 60)

df_prov = pd.read_csv(
    os.path.join(PROC_DIR, "ae_provider_feb2026.csv"),
    parse_dates=["period"]
)

print("  Provider rows loaded: {}".format(len(df_prov)))
print("  Source columns      : {}".format(len(df_prov.columns)))

# --- Select and rename the columns the dashboard needs ---
# Each entry maps: source column name -> output column name.
# Columns not listed here are dropped from the output.
column_map = {
    "period":                                               "period",
    "org_code":                                             "org_code",
    "org_name":                                             "org_name",
    "parent_org":                                           "nhs_region",
    "aande_attendances_type_1":                             "type1_attendances_walkin",
    "aande_attendances_booked_appointments_type_1":         "type1_attendances_booked",
    "attendances_over_4hrs_type_1":                         "over_4hrs_walkin",
    "attendances_over_4hrs_booked_appointments_type_1":     "over_4hrs_booked",
    "patients_who_have_waited_4_12_hs_from_dta_to_admission": "waits_4_12hrs_dta",
    "patients_who_have_waited_12_hrs_from_dta_to_admission":  "waits_12plus_hrs_dta",
    "emergency_admissions_via_aande_type_1":                "emergency_admissions_type1",
    "other_emergency_admissions":                           "other_emergency_admissions",
    "type1_total_attendances":                              "type1_total_attendances",
    "type1_total_over_4hrs":                                "type1_total_over_4hrs",
    "type1_pct_within_4hrs":                                "type1_pct_within_4hrs",
}

# Select only the source columns we want, in the order defined above,
# then rename them all in one operation.
df_prov = df_prov[list(column_map.keys())].rename(columns=column_map)

print("  Output columns      : {}".format(len(df_prov.columns)))

# --- Sort alphabetically by trust name ---
# Alphabetical order makes it easy to find a specific trust when browsing
# the table visual in Power BI. Without sorting, the order reflects the
# original NHS England file order which is not guaranteed to be consistent
# across monthly publications.
df_prov = df_prov.sort_values("org_name").reset_index(drop=True)

# --- Format period as YYYY-MM-DD string ---
df_prov["period"] = df_prov["period"].dt.strftime("%Y-%m-%d")

# --- Save ---
out_prov = os.path.join(OUT_DIR, "powerbi_ready_providers.csv")
df_prov.to_csv(out_prov, index=False)
print("  Saved: {}".format(out_prov))
print("  Rows: {}  |  Columns: {}".format(len(df_prov), len(df_prov.columns)))

type1_count = (df_prov["type1_total_attendances"].fillna(0) > 0).sum()
print("  Providers with Type 1 activity: {}".format(type1_count))
print("  Providers without (walk-in/other only): {}".format(len(df_prov) - type1_count))


print("\n" + "=" * 60)
print("Power BI data prep complete.")
print("  {}".format(out_ts))
print("  {}".format(out_prov))
print("=" * 60)
