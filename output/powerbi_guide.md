# Power BI Dashboard Guide — NHS A&E Performance

## Overview

This guide walks through building an interactive Power BI dashboard from the two CSV files in `output/`:

- `powerbi_ready_timeseries.csv` — 187 rows, national monthly data (Aug 2010–Feb 2026)
- `powerbi_ready_providers.csv` — 198 rows, provider-level snapshot (February 2026)

The finished dashboard should have **3 pages**:
1. **National Overview** — trend lines, headline KPIs, year selector
2. **Trust Performance** — provider rankings, map, scatter plot
3. **Seasonality & Admissions** — heatmap, admissions analysis

---

## Step 1 — Load the Data

1. Open Power BI Desktop → **Get Data → Text/CSV**
2. Load `powerbi_ready_timeseries.csv` → name the table **`TimeSeries`**
3. Load `powerbi_ready_providers.csv` → name the table **`Providers`**

### In Power Query (Transform Data):

**For TimeSeries:**
- Set `period` column type to **Date**
- Set all attendance/admissions columns to **Whole Number**
- Set `pct_within_4hrs` to **Decimal Number**

**For Providers:**
- Set `period` to **Date**
- Set numeric columns to **Whole Number**
- Set `type1_pct_within_4hrs` to **Decimal Number**
- Replace `null` in `type1_pct_within_4hrs` with blank (these are non-Type-1 providers)

### Relationships:
These two tables share a `period` column but represent different grains (national vs provider), so **do not create a relationship between them**. They are analysed independently. Use a **Date Table** (see below) to cross-filter the time series.

---

## Step 2 — Create a Date Table

A dedicated Date Table is best practice in Power BI. It enables time intelligence functions (YTD, rolling averages, YoY comparisons) to work correctly.

In **Home → New Table**, paste this DAX:

```dax
DateTable =
ADDCOLUMNS(
    CALENDAR(DATE(2010,8,1), DATE(2026,12,31)),
    "Year",        YEAR([Date]),
    "MonthNum",    MONTH([Date]),
    "MonthName",   FORMAT([Date], "MMMM"),
    "MonthShort",  FORMAT([Date], "MMM"),
    "YearMonth",   FORMAT([Date], "MMM YYYY"),
    "Quarter",     "Q" & FORMAT(CEILING(MONTH([Date])/3, 1), "0"),
    "FinYear",     IF(MONTH([Date]) >= 4,
                      YEAR([Date]) & "/" & RIGHT(YEAR([Date])+1, 2),
                      YEAR([Date])-1 & "/" & RIGHT(YEAR([Date]), 2))
)
```

**Why a Date Table?** Power BI's time intelligence DAX functions (SAMEPERIODLASTYEAR, TOTALYTD, etc.) require a properly marked, contiguous date table. Without one, year-over-year comparisons and rolling averages will give wrong results.

**Mark as Date Table:** Right-click `DateTable` → Mark as Date Table → Select `Date` column.

**Create relationship:** DateTable[Date] → TimeSeries[period] (Many-to-One, single direction)

---

## Step 3 — DAX Measures

Create a dedicated **Measures** table (Home → Enter Data → blank table named "Measures") to keep all measures organised.

### Core Volume Measures

```dax
Total Attendances =
SUM(TimeSeries[total_attendances])
```
*The total count of all A&E attendances in the selected filter context.*

---

```dax
Type 1 Attendances =
SUM(TimeSeries[type1_attendances])
```
*Major A&E departments only — the primary metric for NHS performance reporting.*

---

```dax
Total Breaches =
SUM(TimeSeries[total_over_4hrs])
```
*Count of patients who waited more than 4 hours. Each breach represents a patient experience failure.*

---

### 4-Hour Performance Measures

```dax
4hr Performance % =
DIVIDE(
    SUM(TimeSeries[total_within_4hrs]),
    SUM(TimeSeries[total_4hr_denominator]),
    BLANK()
)
```
**Why DIVIDE() not `/`?** DIVIDE(numerator, denominator, alternate) handles division by zero gracefully — it returns BLANK() (or your chosen alternate) instead of an error. Using `/` would crash visuals when the denominator is zero (e.g. filtered to a month with no data).

---

```dax
4hr Performance % (Formatted) =
FORMAT([4hr Performance %], "0.0%")
```
*Use this version in card visuals and table tooltips where you want "74.1%" displayed.*

---

```dax
Meetings 78% Standard =
IF([4hr Performance %] >= 0.78, "YES", "NO")
```
*Simple conditional — drives conditional formatting on cards.*

---

### Year-over-Year Measures

```dax
4hr Performance % LY =
CALCULATE(
    [4hr Performance %],
    SAMEPERIODLASTYEAR(DateTable[Date])
)
```
**What SAMEPERIODLASTYEAR does:** It shifts the filter context back by exactly one year. If the current context is Jan–Dec 2025, this measure returns the value for Jan–Dec 2024. Works correctly because we have a marked Date Table.

---

```dax
4hr Performance YoY Change (pp) =
[4hr Performance %] - [4hr Performance % LY]
```
*Year-on-year change in percentage points (pp). Note: this is NOT a percentage-of-percentage — it's the absolute difference. A change from 73% to 74% is +1pp.*

---

```dax
4hr Performance YoY Direction =
VAR change = [4hr Performance YoY Change (pp)]
RETURN
    SWITCH(
        TRUE(),
        ISBLANK(change),     "–",
        change > 0.005,      "▲ Improving",
        change < -0.005,     "▼ Deteriorating",
        "► Flat"
    )
```
**Why SWITCH(TRUE(), ...)?** SWITCH(TRUE()) evaluates each condition in order and returns the first TRUE result — equivalent to a chain of IF/ELSE. It's cleaner than nested IFs when you have 3+ branches. The 0.005 threshold prevents showing "Improving" for a trivial 0.1pp rounding difference.

---

```dax
Attendances YoY Change % =
DIVIDE(
    [Total Attendances] - CALCULATE([Total Attendances], SAMEPERIODLASTYEAR(DateTable[Date])),
    CALCULATE([Total Attendances], SAMEPERIODLASTYEAR(DateTable[Date])),
    BLANK()
)
```

---

### Rolling Average Measures

```dax
4hr Performance 12M Rolling Avg =
CALCULATE(
    [4hr Performance %],
    DATESINPERIOD(DateTable[Date], LASTDATE(DateTable[Date]), -12, MONTH)
)
```
**What DATESINPERIOD does:** Returns a table of dates spanning 12 months back from the last date in context. The rolling average smooths out monthly volatility and shows the underlying trend more clearly than the raw monthly line.

---

### Provider-Level Measures (for Providers page)

```dax
Provider 4hr % =
DIVIDE(
    SUM(Providers[type1_total_attendances]) - SUM(Providers[type1_total_over_4hrs]),
    SUM(Providers[type1_total_attendances]),
    BLANK()
)
```

---

```dax
Providers Meeting Standard =
COUNTROWS(
    FILTER(
        Providers,
        Providers[type1_pct_within_4hrs] >= 78
          && NOT(ISBLANK(Providers[type1_pct_within_4hrs]))
    )
)
```
*Counts how many providers are at or above 78%. Use in a KPI card alongside total provider count.*

---

```dax
Providers Total Type1 =
COUNTROWS(
    FILTER(
        Providers,
        Providers[type1_total_attendances] > 0
    )
)
```

---

```dax
% Providers Meeting Standard =
DIVIDE([Providers Meeting Standard], [Providers Total Type1], BLANK())
```

---

```dax
12+ Hr Waits Total =
SUM(Providers[waits_12plus_hrs_dta])
```
*The most severe patient experience metric — patients waiting 12+ hours after a decision to admit them. NHS England tracks this as a quality indicator.*

---

## Step 4 — Page 1: National Overview

### Layout (1280 x 720 canvas)

```
+----------------------------------------------------------+
|  NHS A&E Performance Dashboard           [Date slicer]   |
+----------------------------------------------------------+
| [KPI: 4hr%]  [KPI: Attendances]  [KPI: Breaches]  [KPI: YoY] |
+----------------------------------------------------------+
|                                                          |
|   Line chart: 4hr performance over time                  |
|   (with 78% reference line)                              |
|                                                          |
+---------------------------+------------------------------+
|  Line chart: Attendances  |  Bar: YoY performance by yr  |
|  trend                    |                              |
+---------------------------+------------------------------+
```

### Visuals to add:

**1. Date Range Slicer**
- Field: `DateTable[Date]`
- Style: Between (slider)
- Default: Last 5 years
- *Why:* Lets users zoom into specific periods (e.g. post-Covid recovery only)

**2. KPI Cards (4 across)**
- Card 1: `[4hr Performance % (Formatted)]` — Title: "4-Hour Performance"
  - Conditional formatting: Red if < 78%, Green if >= 78%
- Card 2: `[Total Attendances]` — format as #,##0
- Card 3: `[Total Breaches]` — format as #,##0, always red
- Card 4: `[4hr Performance YoY Direction]` — show trend direction

**3. Line Chart: 4-Hour Performance Trend**
- X-axis: `DateTable[YearMonth]` (sorted by date)
- Y-axis: `[4hr Performance %]`
- Secondary line: `[4hr Performance 12M Rolling Avg]`
- Format Y-axis: 60% to 100%
- Add constant line at 78% (Analytics pane → Constant Line → 0.78)
- Add constant line at 0.95 with label "Historic 95% target"
- *Why two lines?* The monthly line shows volatility; the rolling average shows the true trend direction

**4. Line Chart: Monthly Attendances**
- X-axis: `DateTable[YearMonth]`
- Values: `[Total Attendances]`, `[Type 1 Attendances]`
- Format Y-axis as millions (#,##0,,"M")

**5. Clustered Bar: Annual Average Performance**
- X-axis: `DateTable[Year]`
- Y-axis: `[4hr Performance %]`
- Conditional colour: Red if < 78%, Green if >= 78%
- *Why:* Lets viewers see the 2022 trough and the slow recovery at a glance

---

## Step 5 — Page 2: Trust Performance

### Visuals:

**1. Region Slicer**
- Field: `Providers[nhs_region]`
- Style: Dropdown or tile buttons

**2. Trust Size Slicer**
- Create a calculated column in Providers:
```dax
Trust Size Band =
SWITCH(
    TRUE(),
    Providers[type1_total_attendances] > 10000, "Large (>10k/month)",
    Providers[type1_total_attendances] >  5000, "Medium (5-10k/month)",
    Providers[type1_total_attendances] >     0, "Small (<5k/month)",
    "Non-Type 1"
)
```

**3. Bar Chart: All Trust Rankings**
- Y-axis: `Providers[org_name]`
- X-axis: `[Provider 4hr %]`
- Sort: Ascending (worst at top or bottom — your preference)
- Conditional colour:
  - Rules: < 0.60 → Red, 0.60–0.78 → Orange, >= 0.78 → Green
- Add constant line at 0.78
- *Why horizontal bars?* Trust names are long. Horizontal bars allow the full name to display without rotation or truncation.

**4. Scatter Chart: Attendances vs Performance**
- X-axis: `Providers[type1_total_attendances]` (volume)
- Y-axis: `[Provider 4hr %]` (performance)
- Size: `Providers[waits_12plus_hrs_dta]` (12+ hr waits = bubble size)
- Details: `Providers[org_name]`
- *Why a scatter?* Shows whether large trusts perform worse than small ones (they do, generally). The bubble size adds a third dimension — the worst performers with the largest bubbles need the most operational attention.

**5. KPI Cards**
- `[Providers Meeting Standard]` / `[Providers Total Type1]` — e.g. "4 of 122"
- `[12+ Hr Waits Total]` — highlight in red
- `[% Providers Meeting Standard]`

**6. Table: Trust Detail**
- Columns: Trust Name, Region, Type 1 Attendances, Breaches, % Within 4hrs, 12+ hr Waits
- Conditional formatting on % Within 4hrs: same colour scale as above
- Sort: by % Within 4hrs ascending

---

## Step 6 — Page 3: Seasonality & Admissions

### Visuals:

**1. Matrix (Heatmap): Seasonal Patterns**
- Rows: `DateTable[Year]`
- Columns: `DateTable[MonthShort]` (sorted by MonthNum)
- Values: `[Total Attendances]`
- Conditional formatting on values: Background colour scale (white → NHS Blue)
- *This replicates the seaborn heatmap in interactive form*

**2. Line Chart: Monthly Seasonality Profile**
- X-axis: `DateTable[MonthName]` (sorted by MonthNum)
- Values: `[Total Attendances]` — Power BI will average across years in this context
- Add a slicer for Year to allow year-specific comparisons

**3. Bar Chart: Admission Rate by Region**
- X-axis: `Providers[nhs_region]`
- Y-axis: `[Provider 4hr %]` — or create an admission rate measure:
```dax
Admission Rate % =
DIVIDE(
    SUM(Providers[emergency_admissions_type1]),
    SUM(Providers[type1_total_attendances]),
    BLANK()
)
```
- Group by Trust Size Band (legend)

**4. KPI: 12+ Hour Waits by Region**
- Clustered bar: Region vs `SUM(Providers[waits_12plus_hrs_dta])`
- Colour: NHS Red — these are all bad, no green needed

---

## Step 7 — Formatting & Design Tips

### Colours
Use the NHS colour palette throughout for a professional, recognisable look:
- Primary blue: `#003087`
- Green (good): `#009639`
- Red (alert): `#DA291C`
- Amber (caution): `#FFB81C`
- Background: `#F0F4F5` (canvas), `#FFFFFF` (visual backgrounds)

### Typography
- Title font: **Segoe UI Semibold**, 14–16pt
- Body: **Segoe UI**, 11pt
- No decorative fonts — NHS reports use clean, accessible sans-serif

### Layout principles
1. **Most important insight top-left** — the eye reads left-to-right, top-to-bottom
2. **KPI cards always at the top** — one number, one label, colour-coded
3. **Consistent visual borders** — subtle 1pt border, light grey (#E8EDEE)
4. **No 3D charts, pie charts, or donut charts** — these distort perception
5. **Every chart needs a title** that states the finding, not just the metric (e.g. "Performance Has Been Below 78% Since 2021" not "4-Hour Performance")

### Slicers
Recommended slicers across all pages:
- Date range (Page 1 and 3)
- NHS Region (Page 2)
- Trust Size Band (Page 2)

Use **sync slicers** (View → Sync Slicers) so region selection on Page 2 persists when navigating to Page 3.

---

## Step 8 — Publishing

1. **Save** as `NHS_AE_Dashboard.pbix`
2. **Publish** to Power BI Service (Home → Publish)
3. In the Service: set a **Scheduled Refresh** if you connect to a live data source later
4. Share via **workspace link** or export as PDF for stakeholders without Power BI licences

---

## Interview Talking Points

**"Why Power BI and not just the Python charts?"**
Power BI adds interactivity — a stakeholder can filter to their region, drill into their specific trust, and answer their own questions without needing a new chart from you. The Python charts are static snapshots; Power BI is a self-service analytical tool.

**"What does the DAX DIVIDE() function do?"**
It's a safe division function that returns BLANK() (not an error) when the denominator is zero. In NHS data, some trusts report zero attendances in some months, so division errors would break visuals. DIVIDE() handles this gracefully.

**"Why SAMEPERIODLASTYEAR rather than just filtering?"**
SAMEPERIODLASTYEAR is context-aware — it works correctly whether the user has filtered to a month, quarter, or year. A manual date filter would need to be rebuilt for every granularity. Time intelligence functions like this are one of Power BI's core strengths.

**"How does the data model work?"**
We have two fact tables (TimeSeries and Providers) connected via a shared Date Table. The Date Table acts as a bridge that lets us cross-filter time periods. The two fact tables are not directly related because they're at different grains (national monthly vs provider monthly snapshot).
