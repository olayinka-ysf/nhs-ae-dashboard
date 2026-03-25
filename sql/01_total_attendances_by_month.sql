-- ============================================================
-- 01_total_attendances_by_month.sql
-- Monthly A&E attendances over the last 3 years
-- ============================================================
--
-- PURPOSE:
--   Show the trend in total A&E attendances for the most recent
--   36 months (3 years). This is the headline volume metric that
--   NHS operational teams track every month.
--
-- DATE FILTERING APPROACH:
--   We use DATEADD(YEAR, -3, MAX(period)) rather than a hardcoded
--   date like '2023-01-01'. WHY? Because this query will still work
--   correctly when new data is loaded next month -- it always looks
--   back exactly 3 years from the latest available data point.
--   Hardcoding dates is a common mistake that causes queries to
--   silently return the wrong time window as data ages.
--
--   DATEADD(YEAR, -3, MAX(period)) means:
--     "take the most recent period in the table, then go back 3 years"
--
-- FORMATTING:
--   FORMAT(period, 'MMM yyyy') converts '2024-01-01' to 'Jan 2024'
--   for readable output. Note: FORMAT() is convenient but slightly
--   slower than CONVERT() -- acceptable for reporting queries.
-- ============================================================

USE NHS_AE_Analysis;
GO

SELECT
    FORMAT(period, 'MMM yyyy')      AS month_label,
    period                          AS period_date,
    type1_attendances               AS major_ae_attendances,
    type2_attendances               AS single_specialty_attendances,
    type3_attendances               AS minor_injury_attendances,
    total_attendances,
    -- Month-on-month change in total attendances
    -- LAG(total_attendances, 1) gets the previous row's value
    -- We divide by the previous value to get % change
    LAG(total_attendances, 1) OVER (ORDER BY period) AS prev_month_total,
    total_attendances
        - LAG(total_attendances, 1) OVER (ORDER BY period)
                                    AS mom_change,
    ROUND(
        CAST(
            total_attendances
            - LAG(total_attendances, 1) OVER (ORDER BY period)
        AS FLOAT)
        / NULLIF(LAG(total_attendances, 1) OVER (ORDER BY period), 0)
        * 100
    , 1)                            AS mom_pct_change
FROM
    dbo.ae_timeseries_activity
WHERE
    period > DATEADD(YEAR, -3, (SELECT MAX(period) FROM dbo.ae_timeseries_activity))
ORDER BY
    period ASC;
