-- ============================================================
-- 06_emergency_admissions_analysis.sql
-- Emergency admissions as % of total attendances by trust type
-- ============================================================
--
-- PURPOSE:
--   Show what proportion of A&E attendances result in an emergency
--   admission, broken down by NHS region and trust size. A higher
--   admission rate can indicate a sicker patient cohort or
--   insufficient community care alternatives.
--
-- WHAT ARE CASE STATEMENTS AND WHEN TO USE THEM?
--
--   CASE is SQL's conditional logic -- equivalent to IF/ELSE or
--   a lookup table. Use CASE when you need to:
--     1. Band/categorise a continuous value (e.g. size buckets)
--     2. Create derived labels from codes
--     3. Conditionally aggregate different subsets
--     4. Replace NULLs with meaningful labels
--
--   Two forms:
--     Simple CASE:   CASE column WHEN value1 THEN ... WHEN value2 THEN ...
--     Searched CASE: CASE WHEN condition1 THEN ... WHEN condition2 THEN ...
--
--   We use the Searched CASE form here because our conditions use
--   comparison operators (> 10000, > 5000) not equality checks.
--
-- TRUST SIZE BANDING:
--   We band trusts by Type 1 attendance volume into Small/Medium/Large.
--   These thresholds are approximate -- a "large" Type 1 A&E typically
--   sees > 100,000 attendances/year, which is ~8,000+/month.
--
-- NULLIF:
--   NULLIF(x, 0) returns NULL when x is 0, preventing division-by-zero
--   errors. Without it, SQL Server would throw an error on any trust
--   with zero attendances in the denominator.
-- ============================================================

USE NHS_AE_Analysis;
GO

WITH provider_calcs AS (
    SELECT
        org_code,
        org_name,
        parent_org                          AS nhs_region,

        -- Total attendances (Type 1 only for consistency)
        type1_total_attendances,

        -- Emergency admissions via Type 1 A&E
        emergency_admissions_type1,

        -- Admission rate: what % of attendances became admissions?
        ROUND(
            CAST(emergency_admissions_type1 AS FLOAT)
            / NULLIF(type1_total_attendances, 0) * 100
        , 1)                                AS admission_rate_pct,

        -- Trust size banding using CASE
        CASE
            WHEN type1_total_attendances > 10000 THEN 'Large (>10k/month)'
            WHEN type1_total_attendances >  5000 THEN 'Medium (5k-10k/month)'
            WHEN type1_total_attendances >     0 THEN 'Small (<5k/month)'
            ELSE 'No Type 1 activity'
        END                                 AS trust_size_band,

        -- Flag trusts with high admission rates (potential pressure indicator)
        CASE
            WHEN CAST(emergency_admissions_type1 AS FLOAT)
                 / NULLIF(type1_total_attendances, 0) > 0.35
                THEN 'High (>35%)'
            WHEN CAST(emergency_admissions_type1 AS FLOAT)
                 / NULLIF(type1_total_attendances, 0) > 0.25
                THEN 'Moderate (25-35%)'
            WHEN CAST(emergency_admissions_type1 AS FLOAT)
                 / NULLIF(type1_total_attendances, 0) > 0
                THEN 'Low (<25%)'
            ELSE 'No data'
        END                                 AS admission_pressure_flag

    FROM dbo.ae_provider_feb2026
    WHERE type1_total_attendances > 0
)
-- Summary by region and trust size
SELECT
    nhs_region,
    trust_size_band,
    COUNT(*)                                AS trust_count,
    SUM(type1_total_attendances)            AS total_type1_attendances,
    SUM(emergency_admissions_type1)         AS total_emerg_admissions,
    ROUND(
        CAST(SUM(emergency_admissions_type1) AS FLOAT)
        / NULLIF(SUM(type1_total_attendances), 0) * 100
    , 1)                                    AS group_admission_rate_pct,
    ROUND(AVG(CAST(admission_rate_pct AS FLOAT)), 1)
                                            AS avg_trust_admission_rate,
    MIN(admission_rate_pct)                 AS min_admission_rate,
    MAX(admission_rate_pct)                 AS max_admission_rate
FROM
    provider_calcs
GROUP BY
    nhs_region,
    trust_size_band
ORDER BY
    nhs_region,
    trust_size_band;
