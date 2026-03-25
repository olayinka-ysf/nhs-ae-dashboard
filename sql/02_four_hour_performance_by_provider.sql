-- ============================================================
-- 02_four_hour_performance_by_provider.sql
-- 4-hour target performance ranked worst to best (Feb 2026)
-- ============================================================
--
-- PURPOSE:
--   Show each Type 1 A&E provider's performance against the
--   4-hour standard, ranked from worst to best. This is the
--   core accountability metric for NHS A&E performance.
--
-- HOW THE PERCENTAGE IS CALCULATED:
--   % within 4 hours = (total attendances - over 4hrs) / total attendances * 100
--   OR equivalently:  = 1 - (breaches / total attendances)
--
--   We pre-calculated this in Python (type1_pct_within_4hrs) and
--   stored it in the table. Here we also show the raw breach count
--   so readers can understand the scale behind the percentage.
--
--   WHY include both? A trust seeing 500 patients at 70% has 150
--   breaches. A trust seeing 15,000 at 70% has 4,500 breaches.
--   The percentage alone hides the operational impact.
--
-- PERFORMANCE BANDING:
--   We use a CASE statement to band performance into categories.
--   The 78% threshold is the current NHS England operational
--   standard (reduced from 95% during the Covid recovery period).
--   In an interview, explain that the 95% target was effectively
--   suspended; 78% is the current floor expectation.
--
-- NULLIF:
--   NULLIF(type1_total_attendances, 0) prevents division by zero
--   for any provider with zero Type 1 attendances. It returns NULL
--   instead of throwing an error.
-- ============================================================

USE NHS_AE_Analysis;
GO

SELECT
    org_code,
    org_name,
    parent_org                          AS nhs_region,
    type1_total_attendances,
    type1_total_over_4hrs               AS breaches,
    type1_pct_within_4hrs               AS pct_within_4hrs,
    -- Performance banding using CASE
    -- CASE evaluates conditions top-to-bottom and returns the first match
    CASE
        WHEN type1_pct_within_4hrs >= 95  THEN 'Excellent (>=95%)'
        WHEN type1_pct_within_4hrs >= 85  THEN 'Good (85-94%)'
        WHEN type1_pct_within_4hrs >= 78  THEN 'Meeting standard (78-84%)'
        WHEN type1_pct_within_4hrs >= 70  THEN 'Below standard (70-77%)'
        WHEN type1_pct_within_4hrs >= 60  THEN 'Poor (60-69%)'
        WHEN type1_pct_within_4hrs IS NOT NULL
                                          THEN 'Critical (<60%)'
        ELSE 'N/A - No Type 1 activity'
    END                                 AS performance_band,
    -- Rank from worst to best (ASC = 1 is worst)
    RANK() OVER (
        ORDER BY type1_pct_within_4hrs ASC
    )                                   AS rank_worst_first
FROM
    dbo.ae_provider_feb2026
WHERE
    type1_total_attendances > 0         -- exclude non-Type 1 providers
ORDER BY
    type1_pct_within_4hrs ASC;          -- worst first
