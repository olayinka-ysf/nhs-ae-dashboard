-- ============================================================
-- 03_seasonal_patterns.sql
-- Seasonal patterns in A&E attendances by month of year
-- ============================================================
--
-- PURPOSE:
--   Identify which calendar months consistently have higher or
--   lower A&E attendances. NHS operational planning uses this
--   to anticipate winter pressures and summer peaks.
--
-- WINDOW FUNCTIONS USED:
--
--   AVG(...) OVER (PARTITION BY month_num)
--   ----------------------------------------
--   PARTITION BY month_num divides the data into 12 groups (one
--   per calendar month). AVG is calculated WITHIN each group.
--   So "avg Jan attendance" is the average across all January
--   rows in the dataset, regardless of year.
--   Without PARTITION BY, AVG would be calculated across ALL rows.
--
--   RANK() OVER (ORDER BY avg_total_attendances DESC)
--   --------------------------------------------------
--   This ranks the 12 months by their average attendance, highest
--   first. RANK() is a window function that assigns a rank based
--   on ORDER BY. Ties get the same rank (e.g. two months both
--   ranked 3), and the next rank is skipped (so there's no rank 4
--   if two months tied at 3).
--
--   In the outer query we use these window-function results to
--   show which months are the busiest. We wrap in a CTE (WITH clause)
--   to compute the per-month aggregates first, then rank them.
--
-- WHY A CTE?
--   We need to aggregate by month first, THEN rank the results.
--   You can't use a window function like RANK() on a column that
--   was itself produced by an aggregate like AVG() in the same
--   SELECT. A CTE lets us do this in two clean logical steps.
-- ============================================================

USE NHS_AE_Analysis;
GO

WITH monthly_averages AS (
    -- Step 1: calculate the average attendance for each calendar month
    -- DATEPART(MONTH, period) extracts the month number (1=Jan, 12=Dec)
    -- FORMAT(period, 'MMMM') gives the full month name (January, etc.)
    SELECT
        DATEPART(MONTH, period)         AS month_num,
        FORMAT(DATEFROMPARTS(2000, DATEPART(MONTH, period), 1), 'MMMM')
                                        AS month_name,
        COUNT(*)                        AS years_of_data,
        AVG(total_attendances)          AS avg_total_attendances,
        AVG(type1_attendances)          AS avg_type1_attendances,
        MIN(total_attendances)          AS min_total_attendances,
        MAX(total_attendances)          AS max_total_attendances,
        -- Coefficient of variation: how much does this month vary year to year?
        -- Higher value = less predictable
        ROUND(
            CAST(STDEV(total_attendances) AS FLOAT)
            / NULLIF(AVG(total_attendances), 0) * 100
        , 1)                            AS variation_pct
    FROM
        dbo.ae_timeseries_activity
    GROUP BY
        DATEPART(MONTH, period)
)
-- Step 2: rank the months and show the seasonal pattern
SELECT
    month_name,
    month_num,
    years_of_data,
    avg_total_attendances,
    avg_type1_attendances,
    min_total_attendances,
    max_total_attendances,
    variation_pct,
    -- How much higher/lower is this month vs the annual average?
    ROUND(
        CAST(avg_total_attendances AS FLOAT)
        / NULLIF(AVG(avg_total_attendances) OVER (), 0) * 100
        - 100
    , 1)                                AS pct_vs_annual_avg,
    RANK() OVER (ORDER BY avg_total_attendances DESC)
                                        AS busiest_rank
FROM
    monthly_averages
ORDER BY
    month_num;
