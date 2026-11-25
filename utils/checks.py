# checks.py
from dataclasses import dataclass
from typing import Any, Optional, Sequence
from sqlalchemy import Engine, table, column, select, func, case, and_, or_, text


@dataclass
class DQResult:
    check_name: str
    dimension: str
    table: str
    column: str
    total_rows: int
    failed_rows: int
    pass_rate: float
    passed: bool
    details: str = ""

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.dimension.upper()} | {self.check_name} | "
            f"{self.table}.{self.column} | "
            f"Pass Rate: {self.pass_rate:.2f}% ({self.failed_rows}/{self.total_rows} failed)"
            + (f" | {self.details}" if self.details else "")
        )


def _build_result(
    check_name: str,
    dimension: str,
    table_name: str,
    col_label: str,
    total: int,
    failed: int,
    threshold: float = 100.0,
    details: str = "",
) -> DQResult:
    total = total or 0
    failed = failed or 0
    pass_rate = 100.0 if total == 0 else ((total - failed) / total) * 100.0
    return DQResult(
        check_name=check_name,
        dimension=dimension,
        table=table_name,
        column=col_label,
        total_rows=total,
        failed_rows=failed,
        pass_rate=pass_rate,
        passed=pass_rate >= threshold,
        details=details,
    )


# ---------------------------------------------------------------------------
# 1. COMPLETENESS
# ---------------------------------------------------------------------------
def check_completeness(
    engine: Engine,
    table_name: str,
    col_name: str,
    schema: Optional[str] = None,
    check_blank_strings: bool = False,
    threshold: float = 100.0,
) -> DQResult:
    """Verify that a column has no NULLs (and optionally no empty/whitespace strings)."""
    col = column(col_name)
    tbl = table(table_name, col, schema=schema)

    if check_blank_strings:
        fail_condition = or_(col.is_(None), func.trim(col) == "")
    else:
        fail_condition = col.is_(None)

    stmt = select(
        func.count().label("total_rows"),
        func.sum(case((fail_condition, 1), else_=0)).label("failed_rows"),
    ).select_from(tbl)

    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().one()

    return _build_result(
        check_name="not_null" + ("_or_blank" if check_blank_strings else ""),
        dimension="completeness",
        table_name=f"{schema}.{table_name}" if schema else table_name,
        col_label=col_name,
        total=row["total_rows"],
        failed=row["failed_rows"],
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# 2. VALIDITY (NULL values are treated as invalid/failed)
# ---------------------------------------------------------------------------
def check_validity_allowed_values(
    engine: Engine,
    table_name: str,
    col_name: str,
    allowed_values: Sequence[Any],
    schema: Optional[str] = None,
    threshold: float = 100.0,
) -> DQResult:
    """Verify values belong to an allowed domain list. NULLs fail."""
    if not allowed_values:
        raise ValueError("allowed_values must not be empty.")

    col = column(col_name)
    tbl = table(table_name, col, schema=schema)

    # Explicitly include col.is_(None) because NULL NOT IN (...) is UNKNOWN in SQL
    fail_condition = or_(col.is_(None), ~col.in_(allowed_values))

    stmt = select(
        func.count().label("total_rows"),
        func.sum(case((fail_condition, 1), else_=0)).label("failed_rows"),
    ).select_from(tbl)

    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().one()

    return _build_result(
        check_name="allowed_values",
        dimension="validity",
        table_name=f"{schema}.{table_name}" if schema else table_name,
        col_label=col_name,
        total=row["total_rows"],
        failed=row["failed_rows"],
        threshold=threshold,
        details=f"Allowed: {list(allowed_values)} (NULLs fail)",
    )


def check_validity_range(
    engine: Engine,
    table_name: str,
    col_name: str,
    min_val: Optional[Any] = None,
    max_val: Optional[Any] = None,
    schema: Optional[str] = None,
    threshold: float = 100.0,
) -> DQResult:
    """Verify values fall within [min_val, max_val]. NULLs fail."""
    col = column(col_name)
    tbl = table(table_name, col, schema=schema)

    bounds = []
    if min_val is not None:
        bounds.append(col < min_val)
    if max_val is not None:
        bounds.append(col > max_val)
    if not bounds:
        raise ValueError("Provide at least one of min_val or max_val.")

    # Explicitly fail NULLs alongside out-of-range values
    fail_condition = or_(col.is_(None), *bounds)

    stmt = select(
        func.count().label("total_rows"),
        func.sum(case((fail_condition, 1), else_=0)).label("failed_rows"),
    ).select_from(tbl)

    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().one()

    return _build_result(
        check_name="value_range",
        dimension="validity",
        table_name=f"{schema}.{table_name}" if schema else table_name,
        col_label=col_name,
        total=row["total_rows"],
        failed=row["failed_rows"],
        threshold=threshold,
        details=f"Expected range [{min_val}, {max_val}] (NULLs fail)",
    )


def check_validity_pattern(
    engine: Engine,
    table_name: str,
    col_name: str,
    like_pattern: str,
    schema: Optional[str] = None,
    threshold: float = 100.0,
) -> DQResult:
    """Verify string values match a SQL LIKE pattern. NULLs fail."""
    col = column(col_name)
    tbl = table(table_name, col, schema=schema)

    # Explicitly include col.is_(None) because NULL NOT LIKE ... is UNKNOWN in SQL
    fail_condition = or_(col.is_(None), ~col.like(like_pattern))

    stmt = select(
        func.count().label("total_rows"),
        func.sum(case((fail_condition, 1), else_=0)).label("failed_rows"),
    ).select_from(tbl)

    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().one()

    return _build_result(
        check_name="like_pattern",
        dimension="validity",
        table_name=f"{schema}.{table_name}" if schema else table_name,
        col_label=col_name,
        total=row["total_rows"],
        failed=row["failed_rows"],
        threshold=threshold,
        details=f"Pattern: {like_pattern} (NULLs fail)",
    )


# ---------------------------------------------------------------------------
# 3. ACCURACY (NULL values are treated as inaccurate/failed)
# ---------------------------------------------------------------------------
def check_accuracy_sql_rule(
    engine: Engine,
    table_name: str,
    rule_name: str,
    valid_sql_predicate: str,
    required_columns: Optional[Sequence[str]] = None,
    schema: Optional[str] = None,
    threshold: float = 100.0,
) -> DQResult:
    """
    Verify row-level business accuracy using a SQL boolean expression that MUST be true.
    - Any row where the predicate evaluates to FALSE or UNKNOWN (due to NULLs) fails.
    - Pass `required_columns` to strictly fail rows where those columns are NULL
      even if the predicate uses OR logic.
    """
    tbl = table(table_name, schema=schema)

    # Parenthesize raw SQL predicate to preserve operator precedence with AND
    pass_clauses = [text(f"({valid_sql_predicate})")]
    if required_columns:
        pass_clauses.extend(column(c).is_not(None) for c in required_columns)

    # Only rows where ALL pass_clauses are strictly TRUE get 0; FALSE/UNKNOWN(NULL) get 1
    stmt = select(
        func.count().label("total_rows"),
        func.sum(case((and_(*pass_clauses), 0), else_=1)).label("failed_rows"),
    ).select_from(tbl)

    with engine.connect() as conn:
        row = conn.execute(stmt).mappings().one()

    return _build_result(
        check_name=rule_name,
        dimension="accuracy",
        table_name=f"{schema}.{table_name}" if schema else table_name,
        col_label=",".join(required_columns) if required_columns else "*",
        total=row["total_rows"],
        failed=row["failed_rows"],
        threshold=threshold,
        details=f"Rule: {valid_sql_predicate} (NULLs fail)",
    )


def check_accuracy_reconciliation(
    source_engine: Engine,
    target_engine: Engine,
    source_table: str,
    target_table: str,
    metric_col: Optional[str] = None,
    source_schema: Optional[str] = None,
    target_schema: Optional[str] = None,
    tolerance: float = 0.0,
    fail_on_nulls: bool = True,
) -> DQResult:
    """
    Cross-database accuracy check: compares COUNT(*) or SUM(metric_col)
    between a source-of-truth DB and a target DB.
    When `metric_col` is given and `fail_on_nulls=True`, any NULL in target's
    `metric_col` causes the check to fail.
    """
    def _get_stats(eng: Engine, tbl_name: str, sch: Optional[str]) -> tuple[float, int]:
        tbl = table(tbl_name, schema=sch)
        if metric_col:
            col = column(metric_col)
            stmt = select(
                func.sum(col).label("metric_val"),
                func.sum(case((col.is_(None), 1), else_=0)).label("null_count"),
            ).select_from(tbl)
        else:
            stmt = select(
                func.count().label("metric_val"),
                func.count().label("unused"),  # placeholder
            ).select_from(tbl)

        with eng.connect() as conn:
            row = conn.execute(stmt).mappings().one()
            metric_val = float(row["metric_val"] or 0.0)
            null_count = int(row["null_count"] or 0) if metric_col else 0
            return metric_val, null_count

    src_val, _ = _get_stats(source_engine, source_table, source_schema)
    tgt_val, tgt_nulls = _get_stats(target_engine, target_table, target_schema)

    diff = abs(src_val - tgt_val)
    passed = (diff <= tolerance) and (not fail_on_nulls or tgt_nulls == 0)

    return DQResult(
        check_name="cross_db_reconciliation",
        dimension="accuracy",
        table=target_table,
        column=metric_col or "ROW_COUNT",
        total_rows=1,
        failed_rows=0 if passed else 1,
        pass_rate=100.0 if passed else 0.0,
        passed=passed,
        details=(
            f"Source={src_val}, Target={tgt_val}, Diff={diff:.4f}"
            + (f", TargetNulls={tgt_nulls}" if metric_col else "")
        ),
    )