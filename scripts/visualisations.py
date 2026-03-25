"""
visualisations.py
-----------------
Connects to SQL Server, pulls the analysis results, and produces five
charts saved to output/charts/.

Charts produced:
  1. line_monthly_attendances.png   -- National A&E attendances trend
  2. line_4hr_performance.png       -- 4-hour target performance over time
  3. bar_top_bottom_trusts.png      -- Best and worst trusts (Feb 2026)
  4. heatmap_seasonal.png           -- Attendance by month and year
  5. bar_admissions_by_region.png   -- Emergency admission rates by region

Run from the project root:
    python scripts/visualisations.py
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import pyodbc
import os

# -- Paths ------------------------------------------------------------------
ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHART_DIR = os.path.join(ROOT, "output", "charts")
os.makedirs(CHART_DIR, exist_ok=True)

# -- SQL Server connection --------------------------------------------------
CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=DESKTOP-4BP374J\\SQLEXPRESS;"
    "DATABASE=NHS_AE_Analysis;"
    "Trusted_Connection=yes;"
)

def query(sql):
    """Run a SQL query and return a pandas DataFrame."""
    conn = pyodbc.connect(CONN_STR)
    df = pd.read_sql(sql, conn)
    conn.close()
    return df


# ==========================================================================
# COLOUR SCHEME
# ==========================================================================
# NHS Identity Guidelines use a specific palette. We adopt these colours
# throughout so every chart looks like it belongs to the same report.
# Using a consistent palette is a mark of professional data presentation.
#
# Key NHS colours:
#   NHS Blue   #003087  -- primary brand colour, used for main series
#   NHS Dark Blue #002060 -- headings, emphasis
#   NHS Mid Green #009639 -- positive/good performance
#   NHS Red    #DA291C  -- alerts, poor performance, breach highlights
#   NHS Warm Yellow #FFB81C -- caution band
#   NHS Grey   #425563  -- secondary data, gridlines
#   NHS Pale Grey #E8EDEE -- background fills

NHS_BLUE       = "#003087"
NHS_DARK_BLUE  = "#002060"
NHS_GREEN      = "#009639"
NHS_RED        = "#DA291C"
NHS_YELLOW     = "#FFB81C"
NHS_GREY       = "#425563"
NHS_PALE_GREY  = "#E8EDEE"
NHS_LIGHT_BLUE = "#41B6E6"

# Global matplotlib style settings applied to all charts
plt.rcParams.update({
    "font.family":       "Arial",
    "font.size":         10,
    "axes.titlesize":    13,
    "axes.titleweight":  "bold",
    "axes.labelsize":    10,
    "axes.spines.top":   False,   # remove top spine for cleaner look
    "axes.spines.right": False,   # remove right spine
    "axes.grid":         True,
    "grid.color":        NHS_PALE_GREY,
    "grid.linewidth":    0.8,
    "figure.facecolor":  "white",
    "axes.facecolor":    "white",
})


# ==========================================================================
# CHART 1: Monthly A&E attendances trend
# ==========================================================================
# WHY a line chart? Line charts are the standard for time-series data.
# They show trends, seasonality, and step-changes clearly.
# We plot all three types (Type 1, Type 2, Type 3) as stacked visual layers
# using fill_between to show composition, with the total as the top line.
# ==========================================================================

print("=" * 55)
print("Chart 1: Monthly A&E attendances trend")
print("=" * 55)

df_act = query("""
    SELECT period, total_attendances, type1_attendances,
           type2_attendances, type3_attendances
    FROM dbo.ae_timeseries_activity
    ORDER BY period
""")
df_act["period"] = pd.to_datetime(df_act["period"])

fig, ax = plt.subplots(figsize=(14, 6))

# Plot total attendances as the primary line
ax.plot(df_act["period"], df_act["total_attendances"] / 1_000_000,
        color=NHS_BLUE, linewidth=2.0, label="Total attendances", zorder=3)

# Shade Type 1 (major A&E) as filled area -- the most clinically significant
ax.fill_between(df_act["period"],
                0,
                df_act["type1_attendances"] / 1_000_000,
                alpha=0.25, color=NHS_BLUE, label="Type 1 (Major A&E)")

# Mark Covid lockdown period -- attendances dropped sharply in 2020
ax.axvspan(pd.Timestamp("2020-03-01"), pd.Timestamp("2020-07-01"),
           alpha=0.12, color=NHS_RED, label="Covid lockdowns (approx)")

# Reference line: pre-pandemic average (2017-2019)
pre_pandemic_avg = df_act[
    (df_act["period"] >= "2017-01-01") & (df_act["period"] < "2020-01-01")
]["total_attendances"].mean() / 1_000_000
ax.axhline(pre_pandemic_avg, color=NHS_GREY, linewidth=1.2,
           linestyle="--", alpha=0.7, label=f"Pre-pandemic avg ({pre_pandemic_avg:.2f}M)")

ax.set_title("NHS A&E Monthly Attendances: England (Aug 2010 – Feb 2026)",
             pad=12)
ax.set_xlabel("Month")
ax.set_ylabel("Attendances (millions)")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}M"))
ax.legend(loc="upper left", framealpha=0.9, fontsize=9)
ax.set_xlim(df_act["period"].min(), df_act["period"].max())

# Footer annotation -- always cite your source on NHS charts
fig.text(0.01, 0.01,
         "Source: NHS England A&E Attendances and Emergency Admissions Statistics",
         fontsize=7, color=NHS_GREY)

plt.tight_layout()
out1 = os.path.join(CHART_DIR, "line_monthly_attendances.png")
plt.savefig(out1, dpi=150, bbox_inches="tight")
plt.close()
print("  Saved:", out1)


# ==========================================================================
# CHART 2: 4-hour target performance over time
# ==========================================================================
# WHY mark the 78% target line? Without context, a reader doesn't know
# whether 74% is good or bad. The target line immediately anchors the
# performance story. We also shade different performance eras to help
# the viewer understand the historical context.
# ==========================================================================

print("\nChart 2: 4-hour target performance over time")

df_perf = query("""
    SELECT period, pct_within_4hrs, total_over_4hrs, total_all
    FROM dbo.ae_timeseries_performance
    ORDER BY period
""")
df_perf["period"] = pd.to_datetime(df_perf["period"])

fig, ax = plt.subplots(figsize=(14, 6))

# Main performance line
ax.plot(df_perf["period"], df_perf["pct_within_4hrs"],
        color=NHS_BLUE, linewidth=2.0, label="% seen within 4 hours", zorder=3)

# Fill green above 95% target (when NHS was meeting it)
ax.fill_between(df_perf["period"], df_perf["pct_within_4hrs"], 95,
                where=df_perf["pct_within_4hrs"] >= 95,
                interpolate=True, alpha=0.25, color=NHS_GREEN,
                label="Above 95% target")

# Fill red below the current 78% standard
ax.fill_between(df_perf["period"], df_perf["pct_within_4hrs"], 78,
                where=df_perf["pct_within_4hrs"] < 78,
                interpolate=True, alpha=0.18, color=NHS_RED,
                label="Below 78% standard")

# Target lines
ax.axhline(95, color=NHS_GREEN, linewidth=1.5, linestyle="--",
           label="95% target (historic)", alpha=0.8)
ax.axhline(78, color=NHS_RED, linewidth=1.5, linestyle="--",
           label="78% current standard", alpha=0.9)

# Annotate the 78% line
ax.annotate("78% current\noperational standard",
            xy=(df_perf["period"].iloc[-1], 78),
            xytext=(-120, -28), textcoords="offset points",
            fontsize=8, color=NHS_RED,
            arrowprops=dict(arrowstyle="->", color=NHS_RED, lw=1.0))

# Covid shading
ax.axvspan(pd.Timestamp("2020-03-01"), pd.Timestamp("2020-07-01"),
           alpha=0.10, color=NHS_YELLOW, label="Covid lockdown")

ax.set_title("NHS A&E 4-Hour Target Performance: England (Nov 2010 – Feb 2026)",
             pad=12)
ax.set_xlabel("Month")
ax.set_ylabel("% seen within 4 hours")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax.set_ylim(60, 100)
ax.set_xlim(df_perf["period"].min(), df_perf["period"].max())
ax.legend(loc="lower left", framealpha=0.9, fontsize=9)

fig.text(0.01, 0.01,
         "Source: NHS England A&E Attendances and Emergency Admissions Statistics",
         fontsize=7, color=NHS_GREY)

plt.tight_layout()
out2 = os.path.join(CHART_DIR, "line_4hr_performance.png")
plt.savefig(out2, dpi=150, bbox_inches="tight")
plt.close()
print("  Saved:", out2)


# ==========================================================================
# CHART 3: Top 10 and Bottom 10 trusts
# ==========================================================================
# WHY a horizontal bar chart? When comparing named entities (trust names
# can be long), horizontal bars allow the labels to be readable without
# rotation. We use diverging colours (green for top, red for bottom) to
# immediately communicate the direction of performance.
# ==========================================================================

print("\nChart 3: Top 10 and bottom 10 trusts")

df_prov = query("""
    SELECT org_name, type1_total_attendances, type1_pct_within_4hrs,
           DENSE_RANK() OVER (ORDER BY type1_pct_within_4hrs DESC) AS rank_best,
           DENSE_RANK() OVER (ORDER BY type1_pct_within_4hrs ASC)  AS rank_worst
    FROM dbo.ae_provider_feb2026
    WHERE type1_total_attendances > 0 AND type1_pct_within_4hrs IS NOT NULL
""")

top10    = df_prov[df_prov["rank_best"]  <= 10].sort_values("type1_pct_within_4hrs")
bottom10 = df_prov[df_prov["rank_worst"] <= 10].sort_values("type1_pct_within_4hrs",
                                                             ascending=False)

# Shorten very long trust names for readability
def shorten(name, max_len=42):
    keywords = [
        "NHS FOUNDATION TRUST", "NHS TRUST", "UNIVERSITY HOSPITALS",
        "FOUNDATION TRUST", "TEACHING HOSPITALS",
    ]
    for kw in keywords:
        name = name.replace(kw, "").strip()
    # Title case
    name = name.title()
    return name[:max_len] + "…" if len(name) > max_len else name

top10    = top10.copy()
bottom10 = bottom10.copy()
top10["label"]    = top10["org_name"].apply(shorten)
bottom10["label"] = bottom10["org_name"].apply(shorten)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
fig.suptitle("NHS A&E 4-Hour Performance: Top 10 and Bottom 10 Trusts\n"
             "February 2026", fontsize=14, fontweight="bold", y=1.01)

# Top 10 -- green bars
bars1 = ax1.barh(top10["label"], top10["type1_pct_within_4hrs"],
                 color=NHS_GREEN, alpha=0.85, height=0.65)
ax1.axvline(78, color=NHS_RED, linewidth=1.5, linestyle="--", alpha=0.8,
            label="78% standard")
ax1.axvline(95, color=NHS_DARK_BLUE, linewidth=1.0, linestyle=":",
            alpha=0.6, label="95% historic target")
ax1.set_title("Top 10 Best Performing", color=NHS_GREEN, fontsize=12)
ax1.set_xlabel("% seen within 4 hours")
ax1.set_xlim(0, 105)
ax1.legend(fontsize=8)
# Data labels
for bar in bars1:
    w = bar.get_width()
    ax1.text(w + 0.5, bar.get_y() + bar.get_height() / 2,
             f"{w:.1f}%", va="center", ha="left", fontsize=8.5,
             color=NHS_DARK_BLUE, fontweight="bold")

# Bottom 10 -- red bars (reversed so worst is at bottom)
bottom10_plot = bottom10.sort_values("type1_pct_within_4hrs")
bars2 = ax2.barh(bottom10_plot["label"], bottom10_plot["type1_pct_within_4hrs"],
                 color=NHS_RED, alpha=0.75, height=0.65)
ax2.axvline(78, color=NHS_RED, linewidth=1.5, linestyle="--", alpha=0.8,
            label="78% standard")
ax2.set_title("Bottom 10 Worst Performing", color=NHS_RED, fontsize=12)
ax2.set_xlabel("% seen within 4 hours")
ax2.set_xlim(0, 105)
ax2.legend(fontsize=8)
for bar in bars2:
    w = bar.get_width()
    ax2.text(w + 0.5, bar.get_y() + bar.get_height() / 2,
             f"{w:.1f}%", va="center", ha="left", fontsize=8.5,
             color=NHS_DARK_BLUE, fontweight="bold")

fig.text(0.01, -0.02,
         "Source: NHS England A&E Attendances and Emergency Admissions Statistics, February 2026",
         fontsize=7, color=NHS_GREY)

plt.tight_layout()
out3 = os.path.join(CHART_DIR, "bar_top_bottom_trusts.png")
plt.savefig(out3, dpi=150, bbox_inches="tight")
plt.close()
print("  Saved:", out3)


# ==========================================================================
# CHART 4: Seasonal heatmap
# ==========================================================================
# WHY a heatmap? A heatmap lets you see two dimensions simultaneously --
# month of year AND calendar year -- in a single compact view.
# It immediately reveals both seasonal patterns (columns) and year-on-year
# trends (rows). This is harder to see in a line chart with 187 points.
#
# We use seaborn's heatmap because it handles the colour scale, labels,
# and annotations automatically. matplotlib alone would require more code.
# Seaborn is built on top of matplotlib -- use seaborn for statistical
# visualisations, matplotlib for fine-grained customisation.
# ==========================================================================

print("\nChart 4: Seasonal attendance heatmap")

df_heat = query("""
    SELECT DATEPART(YEAR, period)  AS yr,
           DATEPART(MONTH, period) AS mo,
           total_attendances
    FROM dbo.ae_timeseries_activity
""")

# Pivot to a matrix: rows = years, columns = months
pivot = df_heat.pivot(index="yr", columns="mo", values="total_attendances")
pivot.columns = ["Jan","Feb","Mar","Apr","May","Jun",
                 "Jul","Aug","Sep","Oct","Nov","Dec"]
pivot = pivot.sort_index(ascending=False)  # most recent year at top

fig, ax = plt.subplots(figsize=(14, 8))

sns.heatmap(
    pivot / 1_000,          # display in thousands
    ax=ax,
    cmap="Blues",           # NHS-appropriate blue palette; darker = more attendances
    annot=True,             # show values in each cell
    fmt=".0f",              # integer format (no decimals)
    linewidths=0.4,
    linecolor="white",
    cbar_kws={"label": "Attendances (thousands)", "shrink": 0.8},
    annot_kws={"size": 7.5},
)

ax.set_title("NHS A&E Monthly Attendances by Year and Month (England)\n"
             "Thousands of attendances — darker = higher demand",
             pad=12)
ax.set_xlabel("Month")
ax.set_ylabel("Year")
ax.tick_params(axis="x", rotation=0)
ax.tick_params(axis="y", rotation=0)

fig.text(0.01, 0.01,
         "Source: NHS England A&E Attendances and Emergency Admissions Statistics",
         fontsize=7, color=NHS_GREY)

plt.tight_layout()
out4 = os.path.join(CHART_DIR, "heatmap_seasonal.png")
plt.savefig(out4, dpi=150, bbox_inches="tight")
plt.close()
print("  Saved:", out4)


# ==========================================================================
# CHART 5: Emergency admission rates by region
# ==========================================================================
# WHY a grouped bar chart? We have two categorical dimensions (region and
# trust size) and one continuous measure (admission rate %). Grouped bars
# show both the within-region size effect and the across-region comparison
# simultaneously. We colour by trust size to make the grouping intuitive.
# ==========================================================================

print("\nChart 5: Emergency admissions by region")

df_adm = query("""
    WITH calcs AS (
        SELECT parent_org AS region,
               CASE WHEN type1_total_attendances > 10000 THEN 'Large (>10k)'
                    WHEN type1_total_attendances >  5000 THEN 'Medium (5-10k)'
                    ELSE 'Small (<5k)' END AS size_band,
               type1_total_attendances,
               emergency_admissions_type1
        FROM dbo.ae_provider_feb2026
        WHERE type1_total_attendances > 0
          AND org_name != 'TOTAL'
    )
    SELECT region, size_band, COUNT(*) AS trust_count,
           SUM(type1_total_attendances) AS total_attendances,
           SUM(emergency_admissions_type1) AS total_admissions,
           ROUND(CAST(SUM(emergency_admissions_type1) AS FLOAT)
                 / NULLIF(SUM(type1_total_attendances),0)*100, 1) AS admission_rate_pct
    FROM calcs
    GROUP BY region, size_band
""")

# Shorten region names
region_short = {
    "NHS ENGLAND EAST OF ENGLAND":          "East of England",
    "NHS ENGLAND LONDON":                   "London",
    "NHS ENGLAND MIDLANDS":                 "Midlands",
    "NHS ENGLAND NORTH EAST AND YORKSHIRE": "NE & Yorkshire",
    "NHS ENGLAND NORTH WEST":               "North West",
    "NHS ENGLAND SOUTH EAST":               "South East",
    "NHS ENGLAND SOUTH WEST":               "South West",
}
df_adm["region_short"] = df_adm["region"].map(region_short).fillna(df_adm["region"])

# Pivot for grouped bar chart
pivot_adm = df_adm.pivot(index="region_short", columns="size_band",
                          values="admission_rate_pct").fillna(0)

# Consistent column order
col_order = [c for c in ["Large (>10k)", "Medium (5-10k)", "Small (<5k)"]
             if c in pivot_adm.columns]
pivot_adm = pivot_adm[col_order]

fig, ax = plt.subplots(figsize=(13, 6))

x = range(len(pivot_adm))
width = 0.25
colours = [NHS_BLUE, NHS_LIGHT_BLUE, NHS_GREY]
offsets = [-width, 0, width]

for i, (col, colour) in enumerate(zip(col_order, colours)):
    bars = ax.bar(
        [xi + offsets[i] for xi in x],
        pivot_adm[col],
        width=width * 0.92,
        color=colour,
        alpha=0.85,
        label=col
    )
    # Data labels on bars taller than 5%
    for bar in bars:
        h = bar.get_height()
        if h > 5:
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.4,
                    f"{h:.1f}%", ha="center", va="bottom",
                    fontsize=7.5, color=NHS_DARK_BLUE)

# National average admission rate reference line
national_rate = (
    df_adm["total_admissions"].sum() / df_adm["total_attendances"].sum() * 100
)
ax.axhline(national_rate, color=NHS_RED, linewidth=1.5, linestyle="--",
           label=f"National avg ({national_rate:.1f}%)")

ax.set_xticks(list(x))
ax.set_xticklabels(pivot_adm.index, rotation=15, ha="right", fontsize=9)
ax.set_title("Emergency Admission Rate by NHS Region and Trust Size\n"
             "Type 1 A&E Providers, February 2026", pad=12)
ax.set_ylabel("Emergency admissions as % of Type 1 attendances")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.set_ylim(0, 45)
ax.legend(title="Trust size (monthly Type 1)", fontsize=9,
          loc="upper right", framealpha=0.9)

fig.text(0.01, 0.01,
         "Source: NHS England A&E Attendances and Emergency Admissions Statistics, February 2026",
         fontsize=7, color=NHS_GREY)

plt.tight_layout()
out5 = os.path.join(CHART_DIR, "bar_admissions_by_region.png")
plt.savefig(out5, dpi=150, bbox_inches="tight")
plt.close()
print("  Saved:", out5)


print("\n" + "=" * 55)
print("All 5 charts saved to output/charts/")
print("=" * 55)
