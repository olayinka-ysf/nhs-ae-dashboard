# NHS A&E Performance Dashboard — Interview Preparation Guide

This guide walks you through every aspect of the project so you can speak confidently about any part of it in an interview. Use it to prepare answers, not to memorise scripts — understand the *why* behind each decision.

---

## PROJECT OVERVIEW

### What is this project, in plain English?

The NHS has a target that 95% of A&E patients should be seen, treated, and either admitted or discharged within 4 hours of arrival. That target was dropped to 78% in 2023 as part of a formal reset. England has not consistently met even the 78% standard in recent years.

This project takes the official monthly NHS England statistics — publicly available data used by NHS boards, the Department of Health, and the media — and builds a complete analytical pipeline around them:

1. **SQL Server** to store and query the data at scale
2. **Python** to clean the data and produce publication-quality charts
3. **Excel** to produce a stakeholder-ready workbook that could be handed to a non-technical NHS manager
4. **Power BI** to create an interactive dashboard that lets users slice by region, trust, and time period

The business problem is real: NHS operational teams need to know *where* performance is worst, *when* it deteriorates seasonally, and *how* this year compares to last year. This project answers those questions.

### Why this dataset?

- It is published by NHS England, so it is authoritative and familiar to NHS interviewers
- It is updated monthly, so the skills you demonstrate are directly transferable to live NHS work
- It covers two granularities: national time series (Aug 2010 – Feb 2026) and provider-level snapshot (198 organisations, Feb 2026)
- It is messy enough to require real cleaning — XLS binary format, multi-row headers, dashes for nulls, string-formatted numbers — but not so messy that cleaning dominates the project

### How would an NHS trust actually use this?

- A **Chief Operating Officer** would use the Power BI dashboard to track whether their trust is above or below the 78% standard this month, and how that compares to last year
- An **NHS England regional team** would use the trust rankings to identify which organisations need improvement support
- A **planning analyst** would use the seasonal heatmap to forecast demand and plan staffing levels for winter
- A **Board assurance committee** would use the Excel workbook as a standing agenda item — formatted for presentation, not raw data

---

## DATA ACQUISITION & CLEANING

### Why these specific data sources?

Two files were downloaded from the NHS England statistics page:

**1. Monthly A&E Time Series (XLS, Aug 2010 – Feb 2026)**
This is the national aggregate — one row per month, showing total attendances by department type and the number seen within/beyond 4 hours. 187 rows. This gives us 15+ years of trend data: pre-pandemic baselines, the Covid drop in 2020, the post-pandemic surge, and the ongoing performance crisis.

**2. February 2026 A&E by Provider (CSV, 198 organisations)**
This is the provider-level snapshot — one row per trust for the most recent month. This gives us the trust-level detail needed for rankings, regional comparisons, and identifying outliers.

Together these two datasets answer both "how is England doing overall?" and "which specific trusts are driving the problem?"

### Every cleaning decision, explained

**File 1 — XLS Time Series:**

- `header=13`: The file has 13 rows of NHS metadata (titles, footnotes, collection dates) before the actual column headers. `header=13` tells pandas to skip directly to row 14. A common mistake is reading the whole file and then dropping rows — specifying `header` is cleaner and more explicit.
- `usecols="B:J"`: Column A is blank. Specifying the column range avoids loading empty columns.
- `engine="xlrd"`: This is the old binary `.xls` format (not `.xlsx`). Modern pandas requires xlrd explicitly for `.xls` files; the default openpyxl engine only handles `.xlsx`.
- `dropna(how="all")`: The sheet has trailing blank rows at the bottom. Dropping fully-empty rows removes these without risking real data loss.
- `format="%b-%y"` for date parsing: Values look like `Aug-10`, `Jan-25`. The `%b` directive handles abbreviated month names; `%y` is 2-digit year. pandas infers the century correctly (2000s).
- `.1` column suffixes: The Performance sheet has two header rows — a group label row and a sub-label row. pandas reads only the sub-label row, so duplicate column names (e.g. two columns both labelled "Type 1 Departments - Major A&E") get a `.1` suffix automatically. We rename these explicitly.

**File 2 — Provider CSV:**

- `snake_case()` function: Column names like `A&E attendances Type 1` contain spaces, ampersands, and mixed case. These are fine in pandas but cause syntax errors in SQL unless quoted. Converting to `snake_case` makes every column name valid as a SQL identifier without escaping.
- `MSitAE-` prefix removal: Period values look like `MSitAE-FEBRUARY-2026`. The prefix is a data collection system identifier — it means nothing analytically. Stripping it and parsing the remainder as a date gives us a proper datetime.
- Dash handling: NHS data uses `-` (a hyphen/dash) to mean "not applicable" — for example, a walk-in centre that does not have Type 1 A&E has a dash in the Type 1 attendance column. We replace dashes with `np.nan` before numeric conversion. Failing to do this leaves the column as `object` dtype and breaks all numeric operations.
- `Int64` vs `int64`: Lowercase `int64` cannot store NaN — pandas would silently convert it to float. Uppercase `Int64` is pandas' nullable integer type, which preserves integer values *and* allows missing values. This matters because some provider columns legitimately have nulls.
- Derived columns: We calculated `type1_total_attendances` as the sum of walk-in and booked appointment Type 1 attendances, and `type1_pct_within_4hrs` as a derived percentage. The same calculation is done again in SQL — this is deliberate. Having it in the CSV makes exploratory analysis faster; doing it in SQL demonstrates SQL skills.

**What I would do differently with messier or larger data:**

- With genuinely messy data (e.g. free-text fields, OCR-extracted PDFs), I would add a data quality log that records every transformation — before/after row counts, null rates, value distributions — so the cleaning is auditable
- With larger data (millions of rows), I would profile with `df.describe()` and `df.value_counts()` before touching it, and use chunked reading (`chunksize` parameter) to avoid memory issues
- For production NHS pipelines, I would add schema validation (e.g. pandera or Great Expectations) to catch upstream data format changes automatically

---

## SQL SERVER

### Why SQL Server?

SQL Server is the dominant RDBMS in the NHS. Most NHS trusts run their data warehouses on SQL Server or Azure SQL Database. Using SQL Server Express (which is free) demonstrates directly applicable skills — not just generic SQL.

### How the database is structured

Two tables were created in the `NHS_AE_Analysis` database:

**`dbo.ae_timeseries_activity`** — 187 rows
National monthly totals: Type 1, Type 2, Type 3 attendances and emergency admissions. One row per month from Aug 2010.

**`dbo.ae_timeseries_performance`** — 185 rows
National monthly 4-hour performance: counts seen within and beyond 4 hours, by department type plus derived total and percentage. Starts Nov 2010 (performance data available slightly later than activity data).

**`dbo.ae_provider_feb2026`** — 198 rows
Provider-level snapshot for February 2026: every NHS trust's attendances, breaches, admissions, 12+ hour waits, and derived 4-hour performance percentage.

### Query-by-query walkthrough

**01_total_attendances_by_month.sql**
Selects the last 3 years of monthly activity, adding month-on-month change using LAG.

Key decision: `DATEADD(YEAR, -3, (SELECT MAX(period) FROM dbo.ae_timeseries_activity))` rather than a hardcoded date. If we hardcoded `'2023-01-01'`, the query would gradually return fewer rows as each new month's data was added. The dynamic approach always returns exactly 36 months regardless of when you run it. This is standard practice for rolling-window reporting queries.

**02_four_hour_performance_by_provider.sql**
Ranks all Type 1 providers by their 4-hour performance percentage, worst to best.

Key decision: `NULLIF(type1_total_attendances, 0)` in the denominator prevents division-by-zero errors for providers with no Type 1 activity in the month. `NULLIF(x, 0)` returns NULL when x is 0, and dividing by NULL returns NULL rather than crashing.

**03_seasonal_patterns.sql**
Uses window functions to show which months have historically highest attendances.

The window function used is:
```sql
AVG(total_attendances) OVER (PARTITION BY DATEPART(MONTH, period))
```
- `PARTITION BY DATEPART(MONTH, period)` creates a separate group for each calendar month (January, February, etc.) regardless of year
- The AVG is computed within each group
- This gives the average January attendance, average February attendance, etc., without needing a GROUP BY that would collapse all the rows

**What PARTITION BY does:** It divides the entire result set into sub-groups (partitions) for the window function to operate on, but unlike GROUP BY it does not collapse the rows. Every row is still present in the output; the window function result is just appended as a new column.

**What ORDER BY inside OVER does:** When used with ranking functions (ROW_NUMBER, RANK, DENSE_RANK, LAG, LEAD), ORDER BY specifies the sequence within each partition. For aggregates like SUM and AVG with a frame clause (ROWS BETWEEN), it defines the order in which rows are accumulated.

**04_year_over_year_comparison.sql**
Uses two chained CTEs and LAG to show year-on-year performance change.

**What is a CTE?** A Common Table Expression is a named temporary result set defined with `WITH name AS (...)`. Think of it like a named view that only exists for the duration of a single query. You can chain them:
```sql
WITH cte1 AS (...),
     cte2 AS (SELECT ... FROM cte1)
SELECT ... FROM cte2
```

**Why use CTEs rather than subqueries?**
- Readability: complex logic is broken into named, sequential steps
- Debuggability: you can run just the CTE body to inspect the intermediate result
- Reusability: within a single query, the same CTE can be referenced multiple times without repeating the logic
- CTEs do not store data — they are recomputed each time they are referenced (unlike a temp table)

**What does LAG() do?** `LAG(column, offset)` is a window function that returns the value from N rows *before* the current row, in the order defined by `OVER (ORDER BY ...)`. `LAG(avg_pct, 1) OVER (ORDER BY performance_year)` returns the previous year's average performance. This is the clean, modern way to do year-on-year comparison — the alternative (a self-join on `year = year - 1`) is more verbose and less readable.

**05_top_bottom_trusts.sql**
Uses DENSE_RANK to identify top and bottom 10 providers, combined with UNION ALL.

**RANK vs DENSE_RANK vs ROW_NUMBER:**

| Function | Ties | Gap after tie? | Use when... |
|---|---|---|---|
| `ROW_NUMBER()` | Different numbers | N/A | You need exactly N unique rows |
| `RANK()` | Same number | Yes (skips) | You want to show there's no 3rd if two tied for 2nd |
| `DENSE_RANK()` | Same number | No | You want consecutive positions without gaps |

Example with scores [90, 85, 85, 70]:
- ROW_NUMBER: 1, 2, 3, 4
- RANK: 1, 2, 2, 4
- DENSE_RANK: 1, 2, 2, 3

We chose DENSE_RANK because we want "the top 10 performance positions" — if two trusts tie for 5th, we want position 6 to follow, not 7 (which RANK would produce).

**UNION vs UNION ALL:** UNION removes duplicate rows (requires an extra sort/comparison step). UNION ALL keeps all rows including duplicates. We use UNION ALL because we know the top 10 and bottom 10 are disjoint sets — no trust can appear in both — so the deduplication step of UNION would be wasted work.

**06_emergency_admissions_analysis.sql**
Categorises trusts by admission rate using CASE statements.

**When to use CASE:**
- When you need to bin a continuous value into categories (`CASE WHEN admissions/attendances > 0.3 THEN 'High' ...`)
- When you need conditional aggregation (`SUM(CASE WHEN condition THEN value ELSE 0 END)`)
- When you want to add a derived label column to a result set
- CASE is the SQL equivalent of an `if/elif/else` block in Python

---

## PYTHON & VISUALISATIONS

### How Python connects to SQL Server

`pyodbc` provides the ODBC connection. The connection string specifies:
- `DRIVER={ODBC Driver 17 for SQL Server}` — the ODBC driver name (must be installed)
- `SERVER=DESKTOP-4BP374J\SQLEXPRESS` — the SQL Server instance
- `DATABASE=NHS_AE_Analysis` — the target database
- `Trusted_Connection=yes` — Windows Authentication (no username/password)

`pd.read_sql(sql, conn)` executes a query and returns the result directly as a DataFrame. This is the standard pattern — no manual cursor management needed.

**Why connect to SQL Server rather than reading the CSV directly?** Demonstrating the full pipeline — data in SQL Server, queried from Python — shows you can work in a real analytical environment where the database is the source of truth. Reading from CSV would skip the SQL layer and not show the integration.

### Why each chart type was chosen

**Chart 1 — Line chart: Monthly attendances**
Line charts are the standard for time-series data. They show trends, direction, and continuity. We add a shaded Type 1 area (fill_between) to show composition, a Covid lockdown band to contextualise the 2020 dip, and a pre-pandemic average reference line so viewers immediately have a baseline.

**Chart 2 — Line chart: 4-hour performance**
Same rationale as above, but we add fill_between to shade the area below 78% in red (breach zone) and above 95% in green (historic target zone). This encoding — green = good, red = bad — is immediately readable without a legend.

**Chart 3 — Horizontal bar chart: Top/bottom trusts**
When comparing named categories (trust names), horizontal bars allow the full name to display without rotation or truncation. Vertical bars with rotated labels are harder to read. We use green for the top 10 and red for the bottom 10 — consistent with the NHS colour-coding of performance (green = meeting standard, red = failing).

**Chart 4 — Heatmap: Seasonal patterns**
A heatmap encodes two categorical dimensions (year and month) with a single continuous measure (attendances) as colour intensity. It lets you see both the column pattern (seasonal peaks — typically higher in winter) and the row pattern (year-on-year trend) simultaneously in a compact space. A line chart with 15 overlapping lines would be harder to read.

Seaborn vs matplotlib: seaborn's `heatmap()` handles the colour scale, cell annotations, axis labels, and colourbar automatically. Doing this from scratch in matplotlib would require 30+ additional lines. The rule of thumb: use seaborn for statistical visualisations (heatmaps, violin plots, regression plots); use matplotlib for fine-grained customisation (annotations, custom axes, composite figures).

**Chart 5 — Grouped bar chart: Admissions by region and trust size**
Two categorical dimensions (region and trust size band) against one continuous metric (admission rate). Grouped bars show both within-region variation by trust size and cross-region comparisons simultaneously. A stacked bar would obscure the size-band differences; separate charts per region would make cross-regional comparison harder.

### Python data processing steps explained

- `pd.to_datetime()`: Converts strings to proper datetime objects, enabling date filtering, sorting, and component extraction (year, month)
- `df.pivot()`: Reshapes from long format (year, month, value) to wide format (rows=years, columns=months) — required for the heatmap
- `str.replace()` with `regex=False`: Faster than regex for simple string substitution; `regex=False` is explicit about intent
- `.fillna(0)` on pivot: Some year/month combinations may have no data — `fillna(0)` prevents NaN cells in the heatmap matrix
- `CAST(... AS FLOAT)` in SQL / `.astype(float)` in Python: Integer division in SQL truncates to zero. Casting to float first gives a decimal result

---

## EXCEL

### Why Excel is still important alongside Python and Power BI

Excel remains the universal sharing format in the NHS. A Power BI dashboard requires a Power BI licence to view. A Python script requires a Python environment to run. An Excel file opens on any computer in any NHS trust. For Board papers, exec briefings, and ad-hoc requests, Excel is the practical delivery format.

### How the workbook is structured for a senior stakeholder

The workbook has four sheets, ordered by audience need:

1. **Summary** — headline KPIs (total attendances, average 4-hour performance, most recent month) formatted as a single-page dashboard. A COO who opens this file should be able to answer "are we hitting the target?" in under 10 seconds.

2. **Monthly Trends** — the national time series with an embedded chart. This gives context to the Summary numbers — is performance improving or getting worse?

3. **Trust Rankings** — top and bottom performing trusts with conditional formatting. Green = above 78%; red = below 78%. This is operationally actionable: a regional director can immediately see which trusts need attention.

4. **Data** — the full cleaned dataset. Analysts who need to do further work have the raw numbers available without having to re-run the Python scripts.

### What the conditional formatting rules do

Conditional formatting applies background colour to cells based on their value:
- Green (`#C6EFCE`) for values ≥ 78% — meeting the standard
- Amber (`#FFEB9C`) for values 70–78% — below standard but not critically so
- Red (`#FFC7CE`) for values < 70% — significantly failing

This traffic-light encoding is NHS standard for performance dashboards — most NHS operational reports use the same colour conventions, so the format is immediately familiar to NHS readers.

### openpyxl vs xlsxwriter

Both were listed in requirements.txt. openpyxl is used for reading and writing `.xlsx` files with full formatting control; xlsxwriter is a write-only library with a simpler API for programmatic workbook creation. The build_excel.py script uses openpyxl because we need both read and write capability and full control over cell formatting, styles, and charts.

---

## POWER BI

### Why Power BI is the right tool for the interactive layer

Static charts answer specific pre-defined questions. Power BI lets the audience ask *their own* questions: "show me only London trusts", "what happened in winter 2023?", "how does my trust compare to the regional average?" — all without needing a new chart from the analyst.

Power BI also handles the ongoing update cycle: when next month's data is released, you update the CSVs and click Refresh — all charts, measures, and KPIs update automatically.

### How the data model works

Two fact tables are loaded:
- **TimeSeries** — 187 rows, national monthly data
- **Providers** — 198 rows, provider-level snapshot

A **Date Table** (created via DAX) is the bridge for time intelligence. The relationship is: `DateTable[Date] → TimeSeries[period]` (Many-to-One).

The two fact tables are **not directly related to each other** because they operate at different grains: TimeSeries is national/monthly, Providers is trust-level/monthly snapshot. Forcing a relationship between them would cause fan-out (row multiplication) or incorrect aggregations.

**Why relationships matter:** Power BI's filter propagation flows along relationships. Without the Date Table relationship, slicers on the date column would not filter the TimeSeries visuals correctly. Without marking the Date Table as the official date table, time intelligence DAX functions (SAMEPERIODLASTYEAR, TOTALYTD) would not work.

### What each DAX measure does in plain English

**`4hr Performance %`** — divides total patients seen within 4 hours by total patients, using DIVIDE() to return blank (not an error) when the denominator is zero.

**`4hr Performance % LY`** — the same calculation but for the same period last year. Uses SAMEPERIODLASTYEAR() which shifts the filter context back 12 months — this works whether the user has filtered to a month, quarter, or year.

**`4hr Performance YoY Change (pp)`** — subtracts last year's performance from this year's. Note this is in *percentage points* (pp), not percent-of-percent. A change from 73% to 75% is +2pp.

**`4hr Performance YoY Direction`** — uses SWITCH(TRUE(), ...) to classify the change as "Improving", "Deteriorating", or "Flat". SWITCH(TRUE()) evaluates each condition in order and returns the first TRUE result — equivalent to a chain of IF/ELSE but cleaner when there are 3+ branches. The 0.005 threshold prevents showing "Improving" for trivial rounding differences.

**`4hr Performance 12M Rolling Avg`** — uses DATESINPERIOD() to calculate performance over the 12 months ending at the current date in context. This smooths out monthly volatility and makes the underlying trend direction clearer.

**`Providers Meeting Standard`** — counts the rows in the Providers table where Type 1 performance ≥ 78% and attendance is non-null. This powers the KPI card "X of Y providers meeting standard."

**Why DIVIDE() not `/`?** `/` throws a division-by-zero error in Power BI when the denominator is 0, breaking the visual. DIVIDE(a, b, BLANK()) returns BLANK() gracefully. BLANK() in Power BI is treated as "no value" — it is excluded from aggregations and displays as empty in cards.

---

## BUSINESS INSIGHTS

### What the key findings mean for NHS operational decision-making

The data shows England has not consistently met the 4-hour A&E target since 2013, and performance fell further after the pandemic. As of February 2026:

- National 4-hour performance is below the 78% operational standard
- There is wide variation between trusts — the best performers are above 95%; the worst are below 60%
- Attendances show clear winter peaks (December–January), consistent across years, confirming the seasonal staffing challenge is structural, not random
- Emergency admission rates vary significantly by region and trust size — larger trusts admit a higher proportion of attendees, reflecting their role as major acute centres

**Operational actions an NHS trust could take based on this analysis:**
- Use the seasonal heatmap to justify requesting additional winter surge capacity (beds, staff) in the annual operational plan
- Use the trust rankings to identify peer organisations performing better with similar volumes, and initiate benchmarking visits
- Use the YoY comparison to demonstrate performance trajectory to the Board — a trust improving from 68% to 72% is moving in the right direction even though it is below the standard
- Use the 12+ hour wait data (available in the provider dataset) to identify the most severe patient experience failures requiring urgent intervention

### Common interview questions and strong answers

**"Why did NHS A&E performance decline after 2013?"**
Multiple factors: growing attendance volumes (partly driven by gaps in primary care access), increasing complexity of presentations (older patients with multiple conditions), bed capacity that has not kept pace with demand, and staffing shortages particularly in emergency medicine. The 4-hour target also has critics who argue it was gamed — trusts moved patients to 'corridors' or 'decision areas' to stop the clock. The 2023 reset to 78% acknowledged the original 95% target was unachievable under current constraints.

**"What would you do if you found an error in the data after publishing?"**
Document the error, quantify its impact, and communicate proactively to stakeholders — don't wait for them to notice. Issue a corrected version with a clear change log. In a production pipeline, add a validation check to prevent the same error recurring. In this project, the derived `type1_pct_within_4hrs` is cross-checked against the published performance figure in the time series as a sanity check.

**"Why not just use Excel for the whole project?"**
Excel handles the analysis and presentation well for small to medium datasets, but it has limitations: no version control, no automated testing, not reproducible by a third party, and it does not scale to millions of rows or complex join logic. SQL handles the querying and data storage at scale; Python handles automation, reproducibility, and complex transformations; Power BI handles interactivity and regular reporting. Each tool is chosen for what it does best.

**"Can you explain what a window function is?"**
A window function performs a calculation across a set of rows related to the current row — the "window" — without collapsing those rows the way GROUP BY does. Every row remains in the output; the window function result is appended as an extra column. Examples: `LAG()` to look at the previous row, `RANK()` to assign a position, `SUM() OVER()` to calculate a running total. They are essential for the kind of period-over-period, ranking, and rolling average calculations that appear constantly in operational NHS reporting.

**"How would you scale this to cover all NHS trusts over multiple years of provider data?"**
The provider CSV currently covers one month. NHS England publishes a file per month. To scale: write a loop in Python to download and process all monthly provider files, union them into a single `ae_provider_historical` table in SQL Server, and update the visualisations and Power BI to use the full time series at provider level. The cleaning logic in clean_data.py is already parametrised by file — extending it to a batch process would be straightforward.

**"What's the difference between a CTE and a subquery?"**
Both produce an intermediate result set that is referenced in the main query. A subquery is inline — embedded directly where it's needed. A CTE is named and defined at the top of the query with `WITH`. CTEs are preferred when: the same subquery is referenced more than once (avoiding repetition), the logic is complex enough that naming the step improves readability, or you want to debug intermediate steps by running just that part. Performance is usually equivalent; in some cases SQL Server optimises CTEs differently.

---

*This guide was written alongside the project in March 2026. Data covers Aug 2010 – Feb 2026.*
