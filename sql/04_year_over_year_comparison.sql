-- ============================================================
-- 04_year_over_year_comparison.sql
-- Year-over-year 4-hour target performance using CTEs and LAG
-- ============================================================
--
-- PURPOSE:
--   Compare each year's average 4-hour performance against the
--   previous year. Shows whether the NHS is improving, plateauing,
--   or deteriorating on the headline target over time.
--
-- WHAT IS A CTE?
--   CTE = Common Table Expression. It's a named temporary result
--   set defined with the WITH keyword. Think of it like creating
--   a "virtual table" that only exists for the duration of the query.
--
--   WHY use a CTE rather than a subquery?
--     - Readability: the logic is separated into named steps
--     - Reusability: you can reference the same CTE multiple times
--     - Debugging: you can run just the CTE part to check it
--
--   We use TWO CTEs here, chained together:
--     1. yearly_perf: aggregate to annual averages
--     2. with_lag:    apply LAG() to get the previous year's value
--   Then the final SELECT adds the year-on-year change calculation.
--
-- WHAT DOES LAG() DO?
--   LAG(column, offset) looks back N rows in the result set and
--   returns that row's value for the specified column.
--   LAG(avg_pct_within_4hrs, 1) means "give me the value from
--   the row that comes 1 position before this one, ordered by year."
--
--   WHY use LAG instead of a self-join?
--     A self-join (joining the table to itself on year = year - 1)
--     would work but is harder to read and less performant.
--     LAG() is the modern, clean SQL Server approach.
--
--   OVER (ORDER BY performance_year) tells LAG which direction to
--   look: ordered by year ascending, so LAG(1) = previous year.
-- ============================================================

USE NHS_AE_Analysis;
GO

WITH yearly_perf AS (
    -- Step 1: aggregate monthly performance to annual averages
    SELECT
        DATEPART(YEAR, period)              AS performance_year,
        COUNT(*)                            AS months_of_data,
        ROUND(AVG(CAST(pct_within_4hrs AS FLOAT)), 1)
                                            AS avg_pct_within_4hrs,
        ROUND(MIN(pct_within_4hrs), 1)      AS worst_month_pct,
        ROUND(MAX(pct_within_4hrs), 1)      AS best_month_pct,
        SUM(total_within_4hrs)              AS total_seen_within_4hrs,
        SUM(total_over_4hrs)                AS total_breaches,
        SUM(total_all)                      AS total_all_attendances
    FROM
        dbo.ae_timeseries_performance
    GROUP BY
        DATEPART(YEAR, period)
),
with_lag AS (
    -- Step 2: attach the previous year's performance using LAG
    SELECT
        performance_year,
        months_of_data,
        avg_pct_within_4hrs,
        worst_month_pct,
        best_month_pct,
        total_seen_within_4hrs,
        total_breaches,
        total_all_attendances,
        LAG(avg_pct_within_4hrs, 1) OVER (ORDER BY performance_year)
                                            AS prev_year_pct
    FROM
        yearly_perf
)
-- Step 3: calculate year-on-year change
SELECT
    performance_year,
    months_of_data,
    avg_pct_within_4hrs,
    worst_month_pct,
    best_month_pct,
    total_breaches,
    prev_year_pct,
    -- Year-on-year change in percentage points (not % of %)
    ROUND(avg_pct_within_4hrs - prev_year_pct, 1)
                                            AS yoy_change_pp,
    -- Direction indicator
    CASE
        WHEN avg_pct_within_4hrs > prev_year_pct  THEN 'Improving'
        WHEN avg_pct_within_4hrs < prev_year_pct  THEN 'Deteriorating'
        WHEN prev_year_pct IS NULL                THEN 'No prior year'
        ELSE 'Flat'
    END                                     AS trend_direction
FROM
    with_lag
ORDER BY
    performance_year ASC;
