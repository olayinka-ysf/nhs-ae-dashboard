"""
build_excel.py
--------------
Builds a polished, stakeholder-ready Excel workbook:
  output/excel/nhs_ae_analysis.xlsx

Sheets:
  1. Summary       -- KPI dashboard with key metrics
  2. Monthly Trends -- time-series data + embedded chart
  3. Trust Rankings -- top/bottom trusts with conditional formatting
  4. Data           -- full cleaned provider dataset

WHY xlsxwriter?
  xlsxwriter gives precise control over formatting, charts, and
  conditional formatting when creating workbooks from scratch.
  openpyxl is the better choice when modifying existing files;
  xlsxwriter is faster and has richer chart/format support for
  new workbooks.

Run from the project root:
    python scripts/build_excel.py
"""

import pandas as pd
import pyodbc
import xlsxwriter
import os
from datetime import datetime

# -- Paths ------------------------------------------------------------------
ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR   = os.path.join(ROOT, "output", "excel")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_FILE  = os.path.join(OUT_DIR, "nhs_ae_analysis.xlsx")

# -- Connection -------------------------------------------------------------
CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=DESKTOP-4BP374J\\SQLEXPRESS;"
    "DATABASE=NHS_AE_Analysis;"
    "Trusted_Connection=yes;"
)

def query(sql):
    conn = pyodbc.connect(CONN_STR)
    df = pd.read_sql(sql, conn)
    conn.close()
    return df

print("Fetching data from SQL Server...")

# -- Pull datasets ----------------------------------------------------------
df_monthly = query("""
    SELECT a.period,
           FORMAT(a.period,'MMM yyyy')   AS month_label,
           a.total_attendances,
           a.type1_attendances,
           a.type2_attendances,
           a.type3_attendances,
           a.total_emerg_admissions,
           p.pct_within_4hrs,
           p.total_over_4hrs            AS breaches
    FROM dbo.ae_timeseries_activity a
    LEFT JOIN dbo.ae_timeseries_performance p ON a.period = p.period
    ORDER BY a.period
""")
df_monthly["period"] = pd.to_datetime(df_monthly["period"])

df_providers = query("""
    SELECT org_code, org_name, parent_org AS nhs_region,
           type1_total_attendances,
           type1_total_over_4hrs          AS breaches,
           type1_pct_within_4hrs,
           emergency_admissions_type1,
           patients_waited_12plus_hrs_dta AS waits_12plus_hrs,
           DENSE_RANK() OVER (ORDER BY type1_pct_within_4hrs DESC) AS rank_best,
           DENSE_RANK() OVER (ORDER BY type1_pct_within_4hrs ASC)  AS rank_worst
    FROM dbo.ae_provider_feb2026
    WHERE type1_total_attendances > 0
      AND type1_pct_within_4hrs IS NOT NULL
      AND org_name != 'TOTAL'
    ORDER BY type1_pct_within_4hrs DESC
""")

df_full = query("""
    SELECT period, org_code, org_name, parent_org AS nhs_region,
           aande_attendances_type_1       AS type1_attendances,
           aande_attendances_type_2       AS type2_attendances,
           aande_attendances_other_aande_department AS type3_attendances,
           attendances_over_4hrs_type_1   AS over_4hrs_type1,
           patients_waited_12plus_hrs_dta AS waits_12plus_hrs,
           emergency_admissions_type1,
           type1_total_attendances,
           type1_total_over_4hrs,
           type1_pct_within_4hrs
    FROM dbo.ae_provider_feb2026
    ORDER BY org_name
""")

# -- Compute KPIs for Summary sheet ----------------------------------------
latest_month   = df_monthly.iloc[-1]
prev_month     = df_monthly.iloc[-2]
latest_label   = latest_month["month_label"]

national_4hr   = float(latest_month["pct_within_4hrs"]) if pd.notna(latest_month["pct_within_4hrs"]) else None
prev_4hr       = float(prev_month["pct_within_4hrs"])   if pd.notna(prev_month["pct_within_4hrs"])   else None
change_4hr     = round(national_4hr - prev_4hr, 1)      if (national_4hr and prev_4hr) else None

total_att      = int(latest_month["total_attendances"])
prev_att       = int(prev_month["total_attendances"])
change_att     = total_att - prev_att

best_trust     = df_providers.iloc[0]
worst_trust    = df_providers[df_providers["rank_worst"] == 1].iloc[0]

type1_providers = int((df_providers["type1_total_attendances"] > 0).sum())
critical_count  = int((df_providers["type1_pct_within_4hrs"] < 60).sum())
meeting_count   = int((df_providers["type1_pct_within_4hrs"] >= 78).sum())

print("Building workbook...")

# ==========================================================================
# CREATE WORKBOOK
# ==========================================================================
wb = xlsxwriter.Workbook(OUT_FILE)

# ==========================================================================
# FORMAT LIBRARY
# ==========================================================================
# WHY define formats up front? xlsxwriter formats are reusable objects.
# Defining them once and referencing them throughout keeps the code clean
# and ensures consistency -- the same NHS Blue is used everywhere.

NHS_BLUE      = "#003087"
NHS_DARK_BLUE = "#002060"
NHS_GREEN     = "#009639"
NHS_RED       = "#DA291C"
NHS_YELLOW    = "#FFB81C"
NHS_GREY      = "#425563"
NHS_PALE_GREY = "#E8EDEE"
NHS_LIGHT_BLUE= "#41B6E6"
WHITE         = "#FFFFFF"

def fmt(props):
    return wb.add_format(props)

# Header formats
hdr_title = fmt({"bold": True, "font_size": 18, "font_color": WHITE,
                 "bg_color": NHS_BLUE, "align": "left", "valign": "vcenter",
                 "font_name": "Arial"})
hdr_section = fmt({"bold": True, "font_size": 11, "font_color": WHITE,
                   "bg_color": NHS_BLUE, "align": "center", "valign": "vcenter",
                   "font_name": "Arial", "border": 1, "border_color": WHITE})
hdr_col = fmt({"bold": True, "font_size": 10, "font_color": WHITE,
               "bg_color": NHS_DARK_BLUE, "align": "center", "valign": "vcenter",
               "font_name": "Arial", "border": 1, "border_color": NHS_PALE_GREY,
               "text_wrap": True})

# KPI box formats
kpi_value_good = fmt({"bold": True, "font_size": 22, "font_color": NHS_GREEN,
                      "bg_color": NHS_PALE_GREY, "align": "center", "valign": "vcenter",
                      "font_name": "Arial", "border": 2, "border_color": NHS_GREEN})
kpi_value_bad  = fmt({"bold": True, "font_size": 22, "font_color": NHS_RED,
                      "bg_color": NHS_PALE_GREY, "align": "center", "valign": "vcenter",
                      "font_name": "Arial", "border": 2, "border_color": NHS_RED})
kpi_value_neu  = fmt({"bold": True, "font_size": 22, "font_color": NHS_BLUE,
                      "bg_color": NHS_PALE_GREY, "align": "center", "valign": "vcenter",
                      "font_name": "Arial", "border": 2, "border_color": NHS_BLUE})
kpi_label = fmt({"bold": True, "font_size": 9, "font_color": NHS_GREY,
                 "bg_color": NHS_PALE_GREY, "align": "center", "valign": "top",
                 "font_name": "Arial", "text_wrap": True})

# Data formats
num_fmt     = fmt({"num_format": "#,##0", "font_name": "Arial", "font_size": 10,
                   "align": "right", "border": 1, "border_color": NHS_PALE_GREY})
pct_fmt     = fmt({"num_format": "0.0%", "font_name": "Arial", "font_size": 10,
                   "align": "right", "border": 1, "border_color": NHS_PALE_GREY})
pct_plain   = fmt({"num_format": '0.0"%"', "font_name": "Arial", "font_size": 10,
                   "align": "right", "border": 1, "border_color": NHS_PALE_GREY})
text_fmt    = fmt({"font_name": "Arial", "font_size": 10,
                   "border": 1, "border_color": NHS_PALE_GREY})
text_wrap   = fmt({"font_name": "Arial", "font_size": 10, "text_wrap": True,
                   "border": 1, "border_color": NHS_PALE_GREY})
date_fmt    = fmt({"num_format": "mmm yyyy", "font_name": "Arial", "font_size": 10,
                   "align": "center", "border": 1, "border_color": NHS_PALE_GREY})

# Alternating row formats
row_even = fmt({"font_name": "Arial", "font_size": 10,
                "bg_color": "#F5F8FA", "border": 1, "border_color": NHS_PALE_GREY})
row_odd  = fmt({"font_name": "Arial", "font_size": 10,
                "bg_color": WHITE, "border": 1, "border_color": NHS_PALE_GREY})
num_even = fmt({"num_format": "#,##0", "font_name": "Arial", "font_size": 10,
                "bg_color": "#F5F8FA", "align": "right",
                "border": 1, "border_color": NHS_PALE_GREY})
num_odd  = fmt({"num_format": "#,##0", "font_name": "Arial", "font_size": 10,
                "bg_color": WHITE, "align": "right",
                "border": 1, "border_color": NHS_PALE_GREY})
pct_even = fmt({"num_format": '0.0"%"', "font_name": "Arial", "font_size": 10,
                "bg_color": "#F5F8FA", "align": "right",
                "border": 1, "border_color": NHS_PALE_GREY})
pct_odd  = fmt({"num_format": '0.0"%"', "font_name": "Arial", "font_size": 10,
                "bg_color": WHITE, "align": "right",
                "border": 1, "border_color": NHS_PALE_GREY})

footer_fmt = fmt({"italic": True, "font_size": 8, "font_color": NHS_GREY,
                  "font_name": "Arial"})
note_fmt   = fmt({"font_size": 9, "font_color": NHS_GREY, "font_name": "Arial",
                  "italic": True})


# ==========================================================================
# SHEET 1: SUMMARY
# ==========================================================================

ws_sum = wb.add_worksheet("Summary")
ws_sum.set_tab_color(NHS_BLUE)
ws_sum.set_zoom(90)
ws_sum.hide_gridlines(2)

# Column widths
ws_sum.set_column("A:A", 2)
ws_sum.set_column("B:B", 20)
ws_sum.set_column("C:C", 20)
ws_sum.set_column("D:D", 20)
ws_sum.set_column("E:E", 20)
ws_sum.set_column("F:F", 20)
ws_sum.set_column("G:G", 2)

# Row heights
ws_sum.set_row(0, 8)
ws_sum.set_row(1, 40)
ws_sum.set_row(2, 8)
ws_sum.set_row(3, 28)
ws_sum.set_row(4, 52)
ws_sum.set_row(5, 24)
ws_sum.set_row(6, 8)
ws_sum.set_row(7, 28)
ws_sum.set_row(8, 52)
ws_sum.set_row(9, 24)

# Title banner
ws_sum.merge_range("B2:F2",
    "NHS A&E Performance Dashboard  |  {}".format(latest_label),
    hdr_title)

# -- KPI Row 1: Volume metrics ---------------------------------------------
ws_sum.merge_range("B4:B4", "TOTAL A&E ATTENDANCES", hdr_section)
ws_sum.merge_range("C4:C4", "TYPE 1 ATTENDANCES",     hdr_section)
ws_sum.merge_range("D4:D4", "4-HOUR PERFORMANCE",     hdr_section)
ws_sum.merge_range("E4:E4", "TOTAL BREACHES",          hdr_section)
ws_sum.merge_range("F4:F4", "MoM ATTENDANCE CHANGE",  hdr_section)

ws_sum.write("B5", "{:,.0f}".format(total_att),         kpi_value_neu)
ws_sum.write("C5", "{:,.0f}".format(int(latest_month["type1_attendances"])), kpi_value_neu)
ws_sum.write("D5", "{:.1f}%".format(national_4hr),       kpi_value_bad if national_4hr < 78 else kpi_value_good)
ws_sum.write("E5", "{:,.0f}".format(int(latest_month["breaches"]) if pd.notna(latest_month["breaches"]) else 0), kpi_value_bad)
change_sign = "+" if change_att >= 0 else ""
ws_sum.write("F5", "{}{:,.0f}".format(change_sign, change_att), kpi_value_neu)

ws_sum.write("B6", "England total, all A&E types",        kpi_label)
ws_sum.write("C6", "Major A&E departments only",          kpi_label)
ws_sum.write("D6", "vs 78% current standard (was 95%)",   kpi_label)
ws_sum.write("E6", "Type 1 departments, all providers",   kpi_label)
ws_sum.write("F6", "vs previous month",                    kpi_label)

# -- KPI Row 2: Provider metrics ------------------------------------------
ws_sum.merge_range("B8:B8", "BEST PERFORMING TRUST",   hdr_section)
ws_sum.merge_range("C8:C8", "WORST PERFORMING TRUST",  hdr_section)
ws_sum.merge_range("D8:D8", "TRUSTS MEETING STANDARD", hdr_section)
ws_sum.merge_range("E8:E8", "TRUSTS IN CRITICAL BAND", hdr_section)
ws_sum.merge_range("F8:F8", "TYPE 1 PROVIDERS",        hdr_section)

best_short  = best_trust["org_name"].replace("NHS FOUNDATION TRUST","").replace("NHS TRUST","").strip().title()[:22]
worst_short = worst_trust["org_name"].replace("NHS FOUNDATION TRUST","").replace("NHS TRUST","").strip().title()[:22]

ws_sum.write("B9", "{}\n{:.1f}%".format(best_short,  float(best_trust["type1_pct_within_4hrs"])),  kpi_value_good)
ws_sum.write("C9", "{}\n{:.1f}%".format(worst_short, float(worst_trust["type1_pct_within_4hrs"])), kpi_value_bad)
ws_sum.write("D9", "{} of {}".format(meeting_count, type1_providers),
             kpi_value_bad if meeting_count < type1_providers * 0.5 else kpi_value_good)
ws_sum.write("E9", str(critical_count), kpi_value_bad)
ws_sum.write("F9", str(type1_providers), kpi_value_neu)

ws_sum.write("B10", "Highest 4-hr % in Feb 2026",     kpi_label)
ws_sum.write("C10", "Lowest 4-hr % in Feb 2026",      kpi_label)
ws_sum.write("D10", "Trusts at or above 78% standard",kpi_label)
ws_sum.write("E10", "Trusts below 60% (critical)",    kpi_label)
ws_sum.write("F10", "Reporting Type 1 activity",      kpi_label)

# Separator
ws_sum.set_row(10, 12)

# -- Notes section ---------------------------------------------------------
ws_sum.set_row(11, 16)
ws_sum.merge_range("B12:F12",
    "KEY CONTEXT", hdr_section)
ws_sum.set_row(12, 15)
ws_sum.set_row(13, 15)
ws_sum.set_row(14, 15)
ws_sum.set_row(15, 15)
ws_sum.set_row(16, 15)

notes = [
    "The 4-hour A&E target requires 95% of patients to be admitted, transferred or discharged within 4 hours of arrival.",
    "The 95% target has not been formally met nationally since July 2015. NHS England set an operational standard of 78% during the recovery period.",
    "Type 1 departments are full emergency departments at acute hospitals. Types 2 and 3 are minor injury units and walk-in centres.",
    "Data source: NHS England A&E Attendances and Emergency Admissions Statistics. Published monthly.",
    "National time series covers Aug 2010 - Feb 2026. Provider data is February 2026 only.",
]
for i, note in enumerate(notes):
    ws_sum.merge_range(12+i, 1, 12+i, 5, note, note_fmt)

# Footer
ws_sum.set_row(18, 14)
ws_sum.merge_range("B19:F19",
    "Produced: {}  |  Data: NHS England  |  Analysis: NHS A&E Performance Dashboard".format(
        datetime.today().strftime("%d %B %Y")),
    footer_fmt)

print("  Sheet 1: Summary - done")


# ==========================================================================
# SHEET 2: MONTHLY TRENDS
# ==========================================================================

ws_trend = wb.add_worksheet("Monthly Trends")
ws_trend.set_tab_color(NHS_LIGHT_BLUE)
ws_trend.set_zoom(90)
ws_trend.hide_gridlines(2)
ws_trend.freeze_panes(3, 0)

# Column widths
col_widths = [12, 14, 14, 13, 13, 14, 10, 10]
for i, w in enumerate(col_widths):
    ws_trend.set_column(i, i, w)

# Title
ws_trend.set_row(0, 30)
ws_trend.merge_range("A1:H1", "NHS A&E Monthly Trends: England (Aug 2010 - Feb 2026)", hdr_title)

# Column headers
ws_trend.set_row(1, 30)
headers = ["Period", "Total Attendances", "Type 1 (Major A&E)",
           "Type 2", "Type 3",
           "Emerg Admissions", "% Within 4hrs", "Breaches (Type 1-3)"]
for col, h in enumerate(headers):
    ws_trend.write(1, col, h, hdr_col)

# Data rows
for i, (_, row) in enumerate(df_monthly.iterrows()):
    r = i + 2
    bg = "#F5F8FA" if i % 2 == 0 else WHITE
    base = fmt({"font_name": "Arial", "font_size": 10, "bg_color": bg,
                "border": 1, "border_color": NHS_PALE_GREY})
    nf   = fmt({"num_format": "#,##0", "font_name": "Arial", "font_size": 10,
                "bg_color": bg, "align": "right",
                "border": 1, "border_color": NHS_PALE_GREY})
    pf   = fmt({"num_format": '0.0"%"', "font_name": "Arial", "font_size": 10,
                "bg_color": bg, "align": "right",
                "border": 1, "border_color": NHS_PALE_GREY})
    df_  = fmt({"num_format": "mmm yyyy", "font_name": "Arial", "font_size": 10,
                "align": "center", "bg_color": bg,
                "border": 1, "border_color": NHS_PALE_GREY})

    ws_trend.write_datetime(r, 0, row["period"].to_pydatetime(), df_)
    ws_trend.write_number(r, 1, int(row["total_attendances"])   if pd.notna(row["total_attendances"])   else 0, nf)
    ws_trend.write_number(r, 2, int(row["type1_attendances"])   if pd.notna(row["type1_attendances"])   else 0, nf)
    ws_trend.write_number(r, 3, int(row["type2_attendances"])   if pd.notna(row["type2_attendances"])   else 0, nf)
    ws_trend.write_number(r, 4, int(row["type3_attendances"])   if pd.notna(row["type3_attendances"])   else 0, nf)
    ws_trend.write_number(r, 5, int(row["total_emerg_admissions"]) if pd.notna(row["total_emerg_admissions"]) else 0, nf)
    if pd.notna(row["pct_within_4hrs"]):
        ws_trend.write_number(r, 6, float(row["pct_within_4hrs"]), pf)
    else:
        ws_trend.write_blank(r, 6, pf)
    if pd.notna(row["breaches"]):
        ws_trend.write_number(r, 7, int(row["breaches"]), nf)
    else:
        ws_trend.write_blank(r, 7, nf)

n_rows = len(df_monthly)

# -- Embedded chart: Total attendances + 4-hr performance ------------------
# WHY two chart types on one chart? We want to show both volume (bars)
# and performance (line) together. Excel's combo chart is ideal for this.
# The secondary axis for performance (%) prevents the line being squashed
# by the large attendance numbers.
chart_att = wb.add_chart({"type": "line"})
chart_att.add_series({
    "name":       "Total Attendances",
    "categories": ["Monthly Trends", 2, 0, n_rows + 1, 0],
    "values":     ["Monthly Trends", 2, 1, n_rows + 1, 1],
    "line":       {"color": NHS_BLUE, "width": 1.75},
})
chart_att.add_series({
    "name":       "% Within 4 Hours",
    "categories": ["Monthly Trends", 2, 0, n_rows + 1, 0],
    "values":     ["Monthly Trends", 2, 6, n_rows + 1, 6],
    "line":       {"color": NHS_RED, "width": 1.75, "dash_type": "dash"},
    "y2_axis":    True,
})
chart_att.set_title({"name": "NHS A&E Attendances and 4-Hour Performance"})
chart_att.set_x_axis({"name": "Month", "num_font": {"size": 8}})
chart_att.set_y_axis({"name": "Total Attendances", "num_format": "#,##0,K",
                       "min": 1000000, "num_font": {"size": 8}})
chart_att.set_y2_axis({"name": "% Within 4 Hours", "num_format": '0"%"',
                        "min": 60, "max": 100, "num_font": {"size": 8}})
chart_att.set_legend({"position": "bottom"})
chart_att.set_size({"width": 680, "height": 300})
chart_att.set_chartarea({"border": {"color": NHS_PALE_GREY}})

ws_trend.insert_chart(2, 9, chart_att, {"x_offset": 5, "y_offset": 5})

print("  Sheet 2: Monthly Trends - done")


# ==========================================================================
# SHEET 3: TRUST RANKINGS
# ==========================================================================
# WHY conditional formatting? It lets the reader's eye go immediately to
# the best and worst performers without reading every number. Green for
# good, red for poor is universally understood and mirrors NHS RAG ratings.

ws_rank = wb.add_worksheet("Trust Rankings")
ws_rank.set_tab_color(NHS_GREEN)
ws_rank.set_zoom(90)
ws_rank.hide_gridlines(2)
ws_rank.freeze_panes(3, 0)

# Column widths
ws_rank.set_column("A:A", 6)   # rank
ws_rank.set_column("B:B", 42)  # trust name
ws_rank.set_column("C:C", 22)  # region
ws_rank.set_column("D:D", 14)  # attendances
ws_rank.set_column("E:E", 12)  # breaches
ws_rank.set_column("F:F", 14)  # % within 4hrs
ws_rank.set_column("G:G", 14)  # emerg admissions
ws_rank.set_column("H:H", 14)  # 12+ hr waits

# Title
ws_rank.set_row(0, 30)
ws_rank.merge_range("A1:H1",
    "NHS A&E Trust Rankings by 4-Hour Performance  |  February 2026  |  Type 1 Providers Only",
    hdr_title)

# Column headers
ws_rank.set_row(1, 30)
rank_headers = ["Rank", "Trust Name", "NHS Region",
                "Type 1 Attendances", "Breaches (>4hrs)",
                "% Within 4hrs", "Emerg Admissions", "12+ hr Waits"]
for col, h in enumerate(rank_headers):
    ws_rank.write(1, col, h, hdr_col)

# Data rows (best to worst)
for i, (_, row) in enumerate(df_providers.iterrows()):
    r = i + 2
    bg = "#F5F8FA" if i % 2 == 0 else WHITE

    base_f = fmt({"font_name": "Arial", "font_size": 10, "bg_color": bg,
                  "border": 1, "border_color": NHS_PALE_GREY})
    num_f  = fmt({"num_format": "#,##0", "font_name": "Arial", "font_size": 10,
                  "bg_color": bg, "align": "right",
                  "border": 1, "border_color": NHS_PALE_GREY})
    pct_f  = fmt({"num_format": '0.0"%"', "font_name": "Arial", "font_size": 10,
                  "bg_color": bg, "align": "right", "bold": True,
                  "border": 1, "border_color": NHS_PALE_GREY})
    rank_f = fmt({"num_format": "0", "font_name": "Arial", "font_size": 10,
                  "bg_color": bg, "align": "center", "bold": True,
                  "border": 1, "border_color": NHS_PALE_GREY})

    ws_rank.write_number(r, 0, int(row["rank_best"]),              rank_f)
    ws_rank.write_string(r, 1, str(row["org_name"]).title(),       base_f)
    ws_rank.write_string(r, 2, str(row["nhs_region"]).replace("NHS ENGLAND ","").title(), base_f)
    ws_rank.write_number(r, 3, int(row["type1_total_attendances"]) if pd.notna(row["type1_total_attendances"]) else 0, num_f)
    ws_rank.write_number(r, 4, int(row["breaches"])                if pd.notna(row["breaches"])               else 0, num_f)
    ws_rank.write_number(r, 5, float(row["type1_pct_within_4hrs"]) if pd.notna(row["type1_pct_within_4hrs"])  else 0, pct_f)
    ws_rank.write_number(r, 6, int(row["emergency_admissions_type1"]) if pd.notna(row["emergency_admissions_type1"]) else 0, num_f)
    ws_rank.write_number(r, 7, int(row["waits_12plus_hrs"])        if pd.notna(row["waits_12plus_hrs"])        else 0, num_f)

n_trust_rows = len(df_providers)

# -- Conditional formatting on % Within 4hrs column (F) -------------------
# Three-colour scale: Red (0%) -> Yellow (78%) -> Green (100%)
# This immediately shows where each trust sits relative to the target.
# The 78% midpoint matches the current operational standard.
ws_rank.conditional_format(2, 5, n_trust_rows + 1, 5, {
    "type":     "3_color_scale",
    "min_type": "num",  "min_value": 0,   "min_color": NHS_RED,
    "mid_type": "num",  "mid_value": 78,  "mid_color": NHS_YELLOW,
    "max_type": "num",  "max_value": 100, "max_color": NHS_GREEN,
})

# Highlight 12+ hr waits: any value > 0 flagged red
ws_rank.conditional_format(2, 7, n_trust_rows + 1, 7, {
    "type":     "cell",
    "criteria": ">",
    "value":    0,
    "format":   wb.add_format({"bg_color": "#FFE0E0", "font_color": NHS_RED,
                               "bold": True, "font_name": "Arial",
                               "num_format": "#,##0"}),
})

# Footnote
ws_rank.set_row(n_trust_rows + 2, 14)
ws_rank.merge_range(n_trust_rows + 2, 0, n_trust_rows + 2, 7,
    "Conditional formatting: Green >= 78% (meeting standard), Yellow approaching standard, Red below standard.  "
    "12+ hr waits highlighted red as these represent the most severe patient experience failures.",
    footer_fmt)

print("  Sheet 3: Trust Rankings - done")


# ==========================================================================
# SHEET 4: DATA
# ==========================================================================

ws_data = wb.add_worksheet("Data")
ws_data.set_tab_color(NHS_GREY)
ws_data.set_zoom(85)
ws_data.freeze_panes(2, 0)
ws_data.hide_gridlines(2)

# Title
ws_data.set_row(0, 30)
ws_data.merge_range("A1:M1",
    "Raw Provider Data  |  February 2026  |  All 198 providers",
    hdr_title)

data_cols = [
    ("Period",              8),
    ("Org Code",            9),
    ("Organisation Name",  40),
    ("NHS Region",         22),
    ("Type 1 Attendances", 14),
    ("Type 2 Attendances", 14),
    ("Type 3 Attendances", 14),
    ("Over 4hrs (Type 1)", 14),
    ("12+ hr Waits",       12),
    ("Emerg Admissions",   14),
    ("Total Type1 Att.",   14),
    ("Total Over 4hrs",    12),
    ("% Within 4hrs",      12),
]
for col, (name, width) in enumerate(data_cols):
    ws_data.set_column(col, col, width)
    ws_data.write(1, col, name, hdr_col)

for i, (_, row) in enumerate(df_full.iterrows()):
    r = i + 2
    bg = "#F5F8FA" if i % 2 == 0 else WHITE
    base_f = fmt({"font_name": "Arial", "font_size": 9, "bg_color": bg,
                  "border": 1, "border_color": NHS_PALE_GREY})
    num_f  = fmt({"num_format": "#,##0", "font_name": "Arial", "font_size": 9,
                  "bg_color": bg, "align": "right",
                  "border": 1, "border_color": NHS_PALE_GREY})
    pct_f  = fmt({"num_format": '0.0"%"', "font_name": "Arial", "font_size": 9,
                  "bg_color": bg, "align": "right",
                  "border": 1, "border_color": NHS_PALE_GREY})

    ws_data.write_string(r, 0, str(row["period"])[:7],             base_f)
    ws_data.write_string(r, 1, str(row["org_code"]),               base_f)
    ws_data.write_string(r, 2, str(row["org_name"]).title(),       base_f)
    ws_data.write_string(r, 3, str(row["nhs_region"]).replace("NHS ENGLAND ","").title(), base_f)
    ws_data.write_number(r, 4, int(row["type1_attendances"]) if pd.notna(row["type1_attendances"]) else 0, num_f)
    ws_data.write_number(r, 5, int(row["type2_attendances"]) if pd.notna(row["type2_attendances"]) else 0, num_f)
    ws_data.write_number(r, 6, int(row["type3_attendances"]) if pd.notna(row["type3_attendances"]) else 0, num_f)
    ws_data.write_number(r, 7, int(row["over_4hrs_type1"])   if pd.notna(row["over_4hrs_type1"])   else 0, num_f)
    ws_data.write_number(r, 8, int(row["waits_12plus_hrs"])  if pd.notna(row["waits_12plus_hrs"])  else 0, num_f)
    ws_data.write_number(r, 9, int(row["emergency_admissions_type1"]) if pd.notna(row["emergency_admissions_type1"]) else 0, num_f)
    ws_data.write_number(r,10, int(row["type1_total_attendances"]) if pd.notna(row["type1_total_attendances"]) else 0, num_f)
    ws_data.write_number(r,11, int(row["type1_total_over_4hrs"])   if pd.notna(row["type1_total_over_4hrs"])   else 0, num_f)
    if pd.notna(row["type1_pct_within_4hrs"]):
        ws_data.write_number(r, 12, float(row["type1_pct_within_4hrs"]), pct_f)
    else:
        ws_data.write_blank(r, 12, pct_f)

# Auto-filter on header row
ws_data.autofilter(1, 0, len(df_full) + 1, len(data_cols) - 1)

print("  Sheet 4: Data - done")


# ==========================================================================
# CLOSE AND SAVE
# ==========================================================================
wb.close()
print("\nWorkbook saved: {}".format(OUT_FILE))
print("File size: {:.0f} KB".format(os.path.getsize(OUT_FILE) / 1024))
