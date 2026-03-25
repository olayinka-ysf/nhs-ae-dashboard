-- ============================================================
-- 05_top_bottom_trusts.sql
-- Top 10 and bottom 10 performing trusts (Feb 2026)
-- ============================================================
--
-- PURPOSE:
--   Identify the best and worst performing Type 1 A&E trusts by
--   4-hour performance. This is the kind of analysis a regional
--   NHS England team would use to prioritise support.
--
-- RANK vs DENSE_RANK vs ROW_NUMBER -- EXPLAINED:
--
--   All three are window functions that assign a number to each row.
--   The difference is how they handle TIES (two rows with the same value):
--
--   ROW_NUMBER() -- always assigns a unique sequential number.
--     Ties get different numbers, decided arbitrarily.
--     Use when you need exactly N rows and don't care about ties.
--     Example with values [90, 85, 85, 70]:
--       ROW_NUMBER: 1, 2, 3, 4
--
--   RANK() -- tied rows get the SAME rank, then SKIPS the next rank(s).
--     Use when you want to flag that two trusts are equally ranked,
--     and correctly shows there's no 3rd place if two tied for 2nd.
--     Example with values [90, 85, 85, 70]:
--       RANK: 1, 2, 2, 4  (skips 3)
--
--   DENSE_RANK() -- tied rows get the SAME rank, NO skipping.
--     Use when you want consecutive ranks without gaps.
--     Example with values [90, 85, 85, 70]:
--       DENSE_RANK: 1, 2, 2, 3  (no skip)
--
--   WHY we use DENSE_RANK here:
--     We want "top 10 distinct performance positions". If two trusts
--     tie for 2nd place, we want position 3 to follow, not position 4.
--     This gives a fairer picture than RANK which would skip a position.
--
-- UNION ALL:
--   We combine top 10 and bottom 10 into a single result using UNION ALL.
--   UNION ALL keeps ALL rows including duplicates (fast).
--   UNION removes duplicates (slower, does a sort/comparison).
--   We use UNION ALL because we know there are no duplicates between
--   top 10 and bottom 10 (they're different trusts).
-- ============================================================

USE NHS_AE_Analysis;
GO

WITH ranked AS (
    SELECT
        org_code,
        org_name,
        parent_org                          AS nhs_region,
        type1_total_attendances,
        type1_total_over_4hrs               AS breaches,
        type1_pct_within_4hrs,
        -- Rank best-to-worst (DESC = rank 1 is best performing)
        DENSE_RANK() OVER (
            ORDER BY type1_pct_within_4hrs DESC
        )                                   AS rank_best,
        -- Rank worst-to-best (ASC = rank 1 is worst performing)
        DENSE_RANK() OVER (
            ORDER BY type1_pct_within_4hrs ASC
        )                                   AS rank_worst
    FROM
        dbo.ae_provider_feb2026
    WHERE
        type1_total_attendances > 0
        AND type1_pct_within_4hrs IS NOT NULL
)
-- Top 10 best performing trusts
SELECT
    'Top 10'                            AS group_label,
    rank_best                           AS rank_position,
    org_code,
    org_name,
    nhs_region,
    type1_total_attendances,
    breaches,
    type1_pct_within_4hrs
FROM ranked
WHERE rank_best <= 10

UNION ALL

-- Bottom 10 worst performing trusts
SELECT
    'Bottom 10'                         AS group_label,
    rank_worst                          AS rank_position,
    org_code,
    org_name,
    nhs_region,
    type1_total_attendances,
    breaches,
    type1_pct_within_4hrs
FROM ranked
WHERE rank_worst <= 10

ORDER BY
    group_label DESC,                   -- Top 10 first, then Bottom 10
    rank_position ASC;
