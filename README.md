# Python Data Quality (DQ) Tool

A lightweight, **SQL-pushdown** Data Quality CLI tool built with Python and SQLAlchemy 2.0+.  
Instead of loading entire tables into Python memory, all checks compile to native SQL aggregation queries (`COUNT`, `SUM(CASE WHEN ...)`) and execute directly on your database engine.

---

## Key Features

- **Multi-Database Connectors**: Unified support for **MySQL**, **SQL Server**, and **Oracle** (Thin mode).
- **Persistent Interactive Shell**: Connect once and run multiple ad-hoc checks or full rule suites over an active connection pool without re-entering credentials.
- **Core DQ Dimensions**:
  - **Completeness**: `NULL` and optional blank/whitespace string detection.
  - **Validity**: Allowed domain values, numeric/date ranges, portable SQL `LIKE` patterns, and regular expressions (`REGEXP` / `REGEXP_LIKE`).
  - **Accuracy**: Row-level cross-column SQL business rules and programmatic cross-database reconciliation.
- **Strict `NULL` Handling**: `NULL` values are explicitly treated as failed/incorrect in **Completeness**, **Validity**, and **Accuracy** checks.
- **Declarative Rulebooks (Suites)**: Define multi-column and table-level rules in `.json`, `.toml`, or `.yaml` files (Informatica/Soda style).
- **Reporting & Export**: Consistent terminal summary tables (`table.column`, total rows, valid rows, failed rows, valid %) plus **CSV** (Excel-ready UTF-8) and **JSON** exports.

---

## Project Structure

```text
DQ_Tool/
├── connectors.py   # DBConfig dataclass, engine factory (MySQL/SQL Server/Oracle), connection tester
├── checks.py       # DQResult model, pushdown SQL checks, and table report formatter
├── suite.py        # Declarative rulebook loader/runner (.json/.toml/.yaml) & CSV/JSON exporter
├── main.py         # Interactive CLI shell (DQShell)
└── README.md       # Project documentation
```

---

## Prerequisites & Installation

- **Python 3.11+** (required for built-in `tomllib` support)

### 1. Install Dependencies

```bash
pip install sqlalchemy pymysql oracledb pyodbc
```

Optional packages depending on your environment:
- **MySQL 8+ (`caching_sha2_password`)**:
  ```bash
  pip install cryptography
  ```
- **YAML Rulebooks (`.yaml` / `.yml`)**:
  ```bash
  pip install pyyaml
  ```
- **SQL Server**: Install [Microsoft ODBC Driver 17 or 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server).
- **Oracle**: Uses `oracledb` in **Thin mode** by default (no Oracle Instant Client installation required).

### 2. Windows Application Control / WDAC Troubleshooting

If Windows blocks SQLAlchemy's compiled `.pyd` Cython binaries (`ImportError: DLL load failed ... Une stratégie de contrôle d'application a bloqué ce fichier`), reinstall SQLAlchemy in pure-Python mode:

**PowerShell:**
```powershell
$env:DISABLE_SQLALCHEMY_CEXT = "1"
pip install --force-reinstall --no-binary sqlalchemy sqlalchemy
```

**Command Prompt (`cmd.exe`):**
```cmd
set DISABLE_SQLALCHEMY_CEXT=1
pip install --force-reinstall --no-binary sqlalchemy sqlalchemy
```

*(Alternative for strict corporate environments: run the tool inside **WSL2 Ubuntu** or request a `.venv` folder exclusion from IT.)*

---

## Quick Start

Launch the interactive shell:

```bash
python main.py
```

You will see the `dq> ` prompt. Connect to a database first, then run checks or rule suites:

```text
dq> connect --db-type mysql --host 127.0.0.1 --port 3306 --username root --database sakila
Password:
Connected! Server version: (8, 0, 36)

dq (mysql:sakila)> tables
dq (mysql:sakila)> check completeness --table actor --columns first_name last_name --blank
dq (mysql:sakila)> run_suite film_rules.json --export results/film_dq.csv
dq (mysql:sakila)> exit
```

---

## Interactive Shell Command Reference

### 1. Connection & Navigation Commands

| Command | Description |
| :--- | :--- |
| `connect` | Opens and caches a database connection pool for the session |
| `status` | Displays active database type, host, port, and database/service name |
| `tables [schema]` | Lists available tables (optionally filtered by `schema`) |
| `disconnect` | Closes the active connection pool |
| `exit` / `quit` | Disconnects and exits the shell |

#### `connect` Arguments

| Flag | Required | Description |
| :--- | :---: | :--- |
| `--db-type` | Yes | `mysql`, `sqlserver`, or `oracle` |
| `--host` | Yes | Hostname or IP address |
| `--port` | Yes | Port (`3306` MySQL, `1433` SQL Server, `1521` Oracle) |
| `-u`, `--username`, `--user` | Yes | Database username |
| `-p`, `--password` | No | Password (prompts securely via `getpass` if omitted) |
| `-d`, `--database` | No | Database name (MySQL / SQL Server) |
| `--service-name` | Oracle | Oracle service name (required when `--db-type oracle`) |
| `--odbc-driver` | No | SQL Server ODBC driver (default: `ODBC Driver 18 for SQL Server`) |

**Connection Examples:**
```text
# MySQL (prompts for password)
connect --db-type mysql --host 127.0.0.1 --port 3306 --username root --database sakila

# SQL Server
connect --db-type sqlserver --host 127.0.0.1 --port 1433 --username sa --password Secret --database SalesDW

# Oracle
connect --db-type oracle --host oracle.example.com --port 1521 --username dq_user --password Secret --service-name ORCLPDB1
```

---

### 2. Ad-Hoc Check Commands (`check`)

All `check` commands accept multiple columns (space-separated `--columns a b` or comma-separated `--columns a,b`) and an optional `--schema` and `--threshold` (default `100.0`).

#### Completeness
Checks for `NULL` values (and optionally empty/whitespace-only strings with `--blank`).

```text
check completeness --table <table_name> --columns <col1> [<col2> ...] [--blank] [--schema <schema>] [--threshold <pct>]
```

Example:
```text
check completeness --table customer --columns email first_name last_name --blank
```

#### Validity
Checks domain values, numeric/date ranges, `LIKE` patterns, or regular expressions. You may combine multiple validity flags in one command.

```text
check validity --table <table_name> --columns <col1> [<col2> ...] [OPTIONS]
```

| Option | Description |
| :--- | :--- |
| `--allowed <v1> <v2> ...` | Space-separated list of allowed values (quote values with spaces) |
| `--min <num>` | Minimum inclusive value |
| `--max <num>` | Maximum inclusive value |
| `--pattern <like_str>` | Portable SQL `LIKE` pattern (`%` and `_` wildcards) |
| `--regex <regex_str>` | Regular expression (MySQL `REGEXP` & Oracle `REGEXP_LIKE` only) |
| `--schema <schema>` | Optional schema name |
| `--threshold <pct>` | Minimum pass rate % required for `PASS` (default: `100.0`) |

Examples:
```text
# Allowed values
check validity --table film --columns rating --allowed G PG PG-13 R NC-17

# Numeric range
check validity --table film --columns release_year --min 1990 --max 2026

# SQL LIKE pattern
check validity --table actor --columns first_name --pattern "J%"

# Regular expression (anchored to match entire string)
check validity --table actor --columns first_name --regex "^J[a-zA-Z]+$"
```

#### Accuracy
Evaluates a row-level SQL boolean expression that must be `TRUE`.

```text
check accuracy --table <table_name> --rule-name <name> --predicate "<sql_expr>" [--columns <req_cols>] [--schema <schema>] [--threshold <pct>]
```

Example:
```text
check accuracy --table film --columns replacement_cost rental_rate --rule-name replacement_covers_rental --predicate "replacement_cost >= rental_rate"
```

---

### 3. Suite, Report & Export Commands

| Command | Description |
| :--- | :--- |
| `run_suite <file> [--export <path>]` | Executes all rules in a `.json`, `.toml`, or `.yaml` suite file |
| `report [--clear]` | Displays all results accumulated during the current session (or clears history with `--clear`) |
| `export --out <path> [--format csv\|json] [--all]` | Exports the last check/suite run (or entire session with `--all`) |

Examples:
```text
run_suite film_rules.json
run_suite film_rules.json --export reports/film_dq.csv
report
export --out reports/session_dq.json --format json --all
```

---

## Declarative Rulebook (`suite.py`) Format

Rulebooks support **JSON (`.json`)**, **TOML (`.toml`)**, and **YAML (`.yaml` / `.yml`)**.

### Supported Rule Types

| Scope | `type` | Required Keys | Optional Keys |
| :--- | :--- | :--- | :--- |
| Column | `completeness` | — | `blank` (`bool`), `threshold` |
| Column | `validity_allowed` | `allowed` (`list`) | `threshold` |
| Column | `validity_range` | `min` and/or `max` | `threshold` |
| Column | `validity_pattern` | `pattern` (`str`, SQL `LIKE`) | `threshold` |
| Column | `validity_regex` | `regex` (`str`) | `threshold` |
| Table | `accuracy_sql` | `rule_name`, `predicate` | `required_columns` (`list`), `threshold` |

### Example `film_rules.json`

```json
{
  "suite_name": "sakila_film_dq",
  "tables": {
    "film": {
      "schema": null,
      "columns": {
        "title": [
          { "type": "completeness", "blank": true, "threshold": 100.0 }
        ],
        "release_year": [
          { "type": "completeness" },
          { "type": "validity_range", "min": 1990, "max": 2026 }
        ],
        "rating": [
          { "type": "validity_allowed", "allowed": ["G", "PG", "PG-13", "R", "NC-17"] }
        ],
        "rental_rate": [
          { "type": "validity_range", "min": 0.99, "max": 9.99 }
        ]
      },
      "table_rules": [
        {
          "type": "accuracy_sql",
          "rule_name": "replacement_covers_rental",
          "required_columns": ["replacement_cost", "rental_rate"],
          "predicate": "replacement_cost >= rental_rate",
          "threshold": 100.0
        }
      ]
    }
  }
}
```

---

## Output & Export Schema

### Terminal Table Output

Every `check`, `run_suite`, and `report` command renders the same aligned summary table:

```text
----------------------------------------------------------------------------------------------------------------------------------
STATUS | DIMENSION    | CHECK                     | TABLE.COLUMN                      | TOTAL ROWS | VALID ROWS | FAILED ROWS | VALID %
----------------------------------------------------------------------------------------------------------------------------------
PASS   | COMPLETENESS | not_null_or_blank         | film.title                        |      1,000 |      1,000 |           0 | 100.00%
PASS   | COMPLETENESS | not_null                  | film.release_year                 |      1,000 |      1,000 |           0 | 100.00%
PASS   | VALIDITY     | value_range               | film.release_year                 |      1,000 |      1,000 |           0 | 100.00%
PASS   | VALIDITY     | allowed_values            | film.rating                       |      1,000 |      1,000 |           0 | 100.00%
PASS   | VALIDITY     | value_range               | film.rental_rate                  |      1,000 |      1,000 |           0 | 100.00%
PASS   | ACCURACY     | replacement_covers_rental | film.replacement_cost,rental_rate |      1,000 |      1,000 |           0 | 100.00%
----------------------------------------------------------------------------------------------------------------------------------
```

### CSV / JSON Export Fields

Exported records include:
- `executed_at` (UTC ISO-8601 timestamp)
- `status` (`PASS` or `FAIL`)
- `dimension` (`completeness`, `validity`, `accuracy`)
- `check_name`
- `table_column` (`<table>.<column>`)
- `table`, `column`
- `total_rows`, `valid_rows`, `failed_rows`
- `valid_pct` (rounded to 2 decimal places)
- `details`

---

## Data Quality Semantics & Dialect Notes

1. **`NULL` Policy**:
   - Validity checks explicitly treat `NULL` values as failed (`col IS NULL OR ...`) rather than letting SQL three-valued logic (`UNKNOWN`) ignore them.
   - Accuracy SQL rules use `CASE WHEN (<predicate>) THEN 0 ELSE 1 END`, so any `UNKNOWN` result caused by `NULL`s also counts as failed. Pass `--columns` (`required_columns` in suites) to enforce non-null columns even inside `OR` predicates.
2. **Empty Strings (`''`)**:
   - **Oracle** treats `''` as `NULL` automatically.
   - **MySQL** and **SQL Server** distinguish `''` from `NULL`; use `--blank` (or `"blank": true`) on text columns to catch empty/whitespace strings.
3. **Regex Support**:
   - `--regex` works on **MySQL** (`REGEXP`) and **Oracle** (`REGEXP_LIKE`).
   - On **SQL Server**, use `--pattern` (`LIKE`, which natively supports character classes like `[a-zA-Z]` in T-SQL).

---

## Programmatic Python API (Including Cross-DB Reconciliation)

You can also import `connectors.py`, `checks.py`, and `suite.py` directly in Python scripts—for example, to run **cross-database accuracy reconciliation** between Oracle and SQL Server/MySQL:

```python
from connectors import DBConfig, create_db_engine
from checks import check_accuracy_reconciliation

src_engine = create_db_engine(DBConfig(
    db_type="oracle", host="...", port=1521, user="...", password="...", service_name="ORCLPDB1"
))
tgt_engine = create_db_engine(DBConfig(
    db_type="mysql", host="127.0.0.1", port=3306, user="root", password="...", database="dw"
))

res = check_accuracy_reconciliation(
    source_engine=src_engine,
    target_engine=tgt_engine,
    source_table="ORDERS",
    target_table="fact_orders",
    metric_col="total_amount",
    tolerance=0.01,
    fail_on_nulls=True,
)
print(res.summary())
```