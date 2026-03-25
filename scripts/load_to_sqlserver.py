"""
load_to_sqlserver.py
--------------------
Connects to a local SQL Server Express instance, creates the NHS_AE_Analysis
database, creates typed tables, and loads the cleaned CSV data into them.

Connection details:
  Server:     DESKTOP-4BP374J\\SQLEXPRESS
  Auth:       Windows Authentication (Trusted Connection)
  Database:   NHS_AE_Analysis (created by this script)

Run from the project root:
    python scripts/load_to_sqlserver.py
"""

import pandas as pd
import pyodbc
import os
import sys

# -- Paths ------------------------------------------------------------------
ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC_DIR = os.path.join(ROOT, "data", "processed")

# -- Connection string -------------------------------------------------------
# Trusted_Connection=yes means Windows Authentication -- no username/password
# needed. SQL Server trusts the Windows login of whoever runs this script.
# WHY Windows Auth? For local development it's simpler and more secure than
# storing a SQL password in a script file.
SERVER = r"DESKTOP-4BP374J\SQLEXPRESS"
CONN_MASTER = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};"
    "DATABASE=master;"
    "Trusted_Connection=yes;"
)
CONN_DB = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};"
    "DATABASE=NHS_AE_Analysis;"
    "Trusted_Connection=yes;"
)


def get_connection(conn_str):
    """Attempt connection, print helpful error if it fails."""
    try:
        conn = pyodbc.connect(conn_str, timeout=10)
        return conn
    except pyodbc.Error as e:
        print("ERROR: Could not connect to SQL Server.")
        print("  Check that SQL Server Express is running.")
        print("  Error detail: {}".format(str(e)))
        sys.exit(1)


# ==========================================================================
# STEP 1: CREATE DATABASE
# ==========================================================================

print("=" * 60)
print("Connecting to SQL Server master database...")
print("=" * 60)

conn = get_connection(CONN_MASTER)
# autocommit=True is required for CREATE DATABASE -- it cannot run inside a
# transaction (which pyodbc starts automatically by default).
conn.autocommit = True
cursor = conn.cursor()

# IF NOT EXISTS check: safe to re-run this script without errors
cursor.execute("""
    IF NOT EXISTS (
        SELECT name FROM sys.databases WHERE name = 'NHS_AE_Analysis'
    )
    BEGIN
        CREATE DATABASE NHS_AE_Analysis;
        PRINT 'Database NHS_AE_Analysis created.';
    END
    ELSE
        PRINT 'Database NHS_AE_Analysis already exists.';
""")
print("Database check complete.")
conn.close()


# ==========================================================================
# STEP 2: CREATE TABLES
# ==========================================================================
# WHY these specific data types?
#   DATE        - period column; SQL Server DATE uses 3 bytes, ideal for
#                 monthly data. Using DATE rather than VARCHAR means we can
#                 do date arithmetic (DATEDIFF, DATEPART, etc.) natively.
#   INT         - attendance and admission counts; these are whole numbers
#                 and INT (4 bytes) handles values up to ~2.1 billion, more
#                 than enough for monthly NHS figures.
#   DECIMAL(5,1)- percentages like 74.1%; 5 total digits, 1 decimal place.
#                 Using DECIMAL rather than FLOAT avoids floating-point
#                 rounding issues when displaying results.
#   VARCHAR(10) - ODS codes are short alphanumeric codes (max ~10 chars).
#   VARCHAR(100)- Organisation names; 100 chars covers all NHS trust names.
#   VARCHAR(60) - Region names.
# ==========================================================================

print("\n" + "=" * 60)
print("Creating tables in NHS_AE_Analysis...")
print("=" * 60)

conn = get_connection(CONN_DB)
conn.autocommit = True
cursor = conn.cursor()

# -- Table 1: ae_timeseries_activity ---------------------------------------
# National monthly attendance and emergency admission totals (Aug 2010-present)
cursor.execute("""
    IF OBJECT_ID('dbo.ae_timeseries_activity', 'U') IS NOT NULL
        DROP TABLE dbo.ae_timeseries_activity;

    CREATE TABLE dbo.ae_timeseries_activity (
        period                  DATE        NOT NULL,
        type1_attendances       INT,
        type2_attendances       INT,
        type3_attendances       INT,
        total_attendances       INT,
        emerg_admissions_type1  INT,
        emerg_admissions_type2  INT,
        emerg_admissions_type3  INT,
        total_emerg_admissions  INT,
        CONSTRAINT PK_activity PRIMARY KEY (period)
    );
""")
print("  Created: ae_timeseries_activity")

# -- Table 2: ae_timeseries_performance ------------------------------------
# National monthly 4-hour performance data (Nov 2010-present)
cursor.execute("""
    IF OBJECT_ID('dbo.ae_timeseries_performance', 'U') IS NOT NULL
        DROP TABLE dbo.ae_timeseries_performance;

    CREATE TABLE dbo.ae_timeseries_performance (
        period              DATE            NOT NULL,
        type1_within_4hrs   INT,
        type2_within_4hrs   INT,
        type3_within_4hrs   INT,
        total_within_4hrs   INT,
        type1_over_4hrs     INT,
        type2_over_4hrs     INT,
        type3_over_4hrs     INT,
        total_over_4hrs     INT,
        total_all           INT,
        pct_within_4hrs     DECIMAL(5,1),
        CONSTRAINT PK_performance PRIMARY KEY (period)
    );
""")
print("  Created: ae_timeseries_performance")

# -- Table 3: ae_provider_feb2026 ------------------------------------------
# Provider-level snapshot for February 2026 (all 198 providers)
cursor.execute("""
    IF OBJECT_ID('dbo.ae_provider_feb2026', 'U') IS NOT NULL
        DROP TABLE dbo.ae_provider_feb2026;

    CREATE TABLE dbo.ae_provider_feb2026 (
        period                                                  DATE,
        org_code                                                VARCHAR(10)     NOT NULL,
        parent_org                                              VARCHAR(100),
        org_name                                                VARCHAR(150),
        aande_attendances_type_1                                INT,
        aande_attendances_type_2                                INT,
        aande_attendances_other_aande_department                INT,
        aande_attendances_booked_appointments_type_1            INT,
        aande_attendances_booked_appointments_type_2            INT,
        aande_attendances_booked_appointments_other_department  INT,
        attendances_over_4hrs_type_1                            INT,
        attendances_over_4hrs_type_2                            INT,
        attendances_over_4hrs_other_department                  INT,
        attendances_over_4hrs_booked_appointments_type_1        INT,
        attendances_over_4hrs_booked_appointments_type_2        INT,
        attendances_over_4hrs_booked_appointments_other_department INT,
        patients_waited_4_12hrs_dta                             INT,
        patients_waited_12plus_hrs_dta                          INT,
        emergency_admissions_type1                              INT,
        emergency_admissions_type2                              INT,
        emergency_admissions_other                              INT,
        other_emergency_admissions                              INT,
        type1_total_attendances                                 INT,
        type1_total_over_4hrs                                   INT,
        type1_pct_within_4hrs                                   DECIMAL(5,1),
        CONSTRAINT PK_provider PRIMARY KEY (org_code)
    );
""")
print("  Created: ae_provider_feb2026")
conn.close()


# ==========================================================================
# STEP 3: LOAD DATA
# ==========================================================================

def load_csv_to_table(csv_path, table_name, col_map=None):
    """
    Load a cleaned CSV into a SQL Server table using bulk INSERT.

    WHY not use pandas .to_sql()? pandas .to_sql() with pyodbc is very slow
    for large datasets because it inserts row-by-row by default.
    Instead we use executemany() with fast_executemany=True, which batches
    the inserts -- significantly faster for thousands of rows.

    col_map: optional dict to rename CSV columns to match table column names.
    """
    print("\nLoading: {}".format(csv_path))
    df = pd.read_csv(csv_path)

    # Rename columns if a mapping was provided
    if col_map:
        df = df.rename(columns=col_map)

    # Convert pandas nullable integer types (Int64) to plain Python objects.
    # fast_executemany struggles with pandas extension types -- converting to
    # object dtype first ensures pyodbc receives standard Python int/None values.
    for col in df.columns:
        if hasattr(df[col], "dtype") and str(df[col].dtype) in ("Int64", "Int32"):
            df[col] = df[col].astype(object).where(df[col].notna(), None)

    # Replace remaining NaN/NA with None so pyodbc sends SQL NULL
    df = df.where(pd.notnull(df), None)

    conn = get_connection(CONN_DB)
    conn.autocommit = False  # use a transaction for data loading
    cursor = conn.cursor()
    cursor.fast_executemany = True  # batch inserts -- much faster

    # Build the INSERT statement dynamically from the DataFrame columns
    cols = list(df.columns)
    placeholders = ", ".join(["?" for _ in cols])
    col_names = ", ".join(cols)
    sql = "INSERT INTO dbo.{} ({}) VALUES ({})".format(
        table_name, col_names, placeholders
    )

    # Convert DataFrame to list of tuples for executemany.
    # We explicitly convert any remaining NaN/float('nan') to None here.
    # This is necessary because float64 NaN survives df.where(..., None) as
    # np.float64('nan'), which pyodbc sends as "" rather than SQL NULL.
    def clean_val(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        return v

    rows = [tuple(clean_val(v) for v in row)
            for row in df.itertuples(index=False, name=None)]

    try:
        cursor.executemany(sql, rows)
        conn.commit()
        print("  Inserted {} rows into {}".format(len(rows), table_name))
    except pyodbc.Error as e:
        conn.rollback()
        print("  ERROR inserting into {}: {}".format(table_name, str(e)))
        raise
    finally:
        conn.close()

    return len(rows)


print("\n" + "=" * 60)
print("Loading data into SQL Server tables...")
print("=" * 60)

# Load activity time series
load_csv_to_table(
    os.path.join(PROC_DIR, "ae_timeseries_activity.csv"),
    "ae_timeseries_activity"
)

# Load performance time series
load_csv_to_table(
    os.path.join(PROC_DIR, "ae_timeseries_performance.csv"),
    "ae_timeseries_performance"
)

# Load provider data -- the CSV has long snake_case column names that need
# mapping to the shorter table column names for DTA wait columns
provider_col_map = {
    "patients_who_have_waited_4_12_hs_from_dta_to_admission": "patients_waited_4_12hrs_dta",
    "patients_who_have_waited_12_hrs_from_dta_to_admission":  "patients_waited_12plus_hrs_dta",
    "emergency_admissions_via_aande_type_1":                  "emergency_admissions_type1",
    "emergency_admissions_via_aande_type_2":                  "emergency_admissions_type2",
    "emergency_admissions_via_aande_other_aande_department":  "emergency_admissions_other",
}

load_csv_to_table(
    os.path.join(PROC_DIR, "ae_provider_feb2026.csv"),
    "ae_provider_feb2026",
    col_map=provider_col_map
)


# ==========================================================================
# STEP 4: VERIFY ROW COUNTS
# ==========================================================================

print("\n" + "=" * 60)
print("Verifying row counts...")
print("=" * 60)

conn = get_connection(CONN_DB)
cursor = conn.cursor()

tables = [
    "ae_timeseries_activity",
    "ae_timeseries_performance",
    "ae_provider_feb2026",
]

for table in tables:
    cursor.execute("SELECT COUNT(*) FROM dbo.{}".format(table))
    count = cursor.fetchone()[0]
    print("  {}: {} rows".format(table, count))

# Quick sanity check: show the date range in the time series tables
cursor.execute("""
    SELECT
        MIN(period) AS earliest,
        MAX(period) AS latest,
        COUNT(*)    AS row_count
    FROM dbo.ae_timeseries_activity
""")
row = cursor.fetchone()
print("\nActivity date range: {} to {} ({} months)".format(
    row.earliest.strftime("%b %Y"),
    row.latest.strftime("%b %Y"),
    row.row_count
))

cursor.execute("""
    SELECT
        MIN(pct_within_4hrs) AS worst,
        MAX(pct_within_4hrs) AS best,
        AVG(pct_within_4hrs) AS avg_perf
    FROM dbo.ae_timeseries_performance
""")
row = cursor.fetchone()
print("Performance range: {}% (worst) -- {}% (best) -- {}% (avg)".format(
    row.worst, row.best, round(float(row.avg_perf), 1)
))

cursor.execute("""
    SELECT TOP 5
        org_name,
        type1_total_attendances,
        type1_pct_within_4hrs
    FROM dbo.ae_provider_feb2026
    WHERE type1_total_attendances > 0
    ORDER BY type1_pct_within_4hrs ASC
""")
print("\nBottom 5 Type 1 trusts by 4-hour performance (Feb 2026):")
for r in cursor.fetchall():
    print("  {}: {}% ({} attendances)".format(
        r.org_name, r.type1_pct_within_4hrs, r.type1_total_attendances
    ))

conn.close()
print("\nSQL Server loading complete.")
