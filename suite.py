# suite.py
import csv
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from sqlalchemy import Engine
from utils import connectors, checks
from utils.checks import (
    DQResult,
    check_completeness,
    check_validity_allowed_values,
    check_validity_range,
    check_validity_pattern,
    check_accuracy_sql_rule,
)


def load_suite(file_path: str) -> dict:
    """Load a DQ rulebook from .json, .toml, or .yaml/.yml."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Suite file not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    elif suffix == ".toml":
        with path.open("rb") as f:
            return tomllib.load(f)
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML is required for .yaml files (pip install pyyaml) or use .json/.toml.") from exc
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    else:
        raise ValueError(f"Unsupported suite format '{suffix}'. Use .json, .toml, or .yaml.")


def run_suite(engine: Engine, file_path: str) -> list[DQResult]:
    """Execute all column-level and table-level rules in a suite file."""
    suite = load_suite(file_path)
    tables = suite.get("tables", {})
    results: list[DQResult] = []

    for table_name, table_cfg in tables.items():
        schema = table_cfg.get("schema")

        # 1. Column-level rules
        for col_name, rules in table_cfg.get("columns", {}).items():
            for rule in rules:
                rtype = rule["type"]
                threshold = float(rule.get("threshold", 100.0))

                if rtype == "completeness":
                    results.append(
                        check_completeness(
                            engine,
                            table_name=table_name,
                            col_name=col_name,
                            schema=schema,
                            check_blank_strings=rule.get("blank", False),
                            threshold=threshold,
                        )
                    )
                elif rtype == "validity_allowed":
                    results.append(
                        check_validity_allowed_values(
                            engine,
                            table_name=table_name,
                            col_name=col_name,
                            allowed_values=rule["allowed"],
                            schema=schema,
                            threshold=threshold,
                        )
                    )
                elif rtype == "validity_range":
                    results.append(
                        check_validity_range(
                            engine,
                            table_name=table_name,
                            col_name=col_name,
                            min_val=rule.get("min"),
                            max_val=rule.get("max"),
                            schema=schema,
                            threshold=threshold,
                        )
                    )
                elif rtype == "validity_pattern":
                    results.append(
                        check_validity_pattern(
                            engine,
                            table_name=table_name,
                            col_name=col_name,
                            like_pattern=rule["pattern"],
                            schema=schema,
                            threshold=threshold,
                        )
                    )
                elif rtype == "validity_regex":
                    results.append(
                        check_validity_regex(
                            engine,
                            table_name=table_name,
                            col_name=col_name,
                            regex_pattern=rule["regex"],
                            schema=schema,
                            threshold=threshold,
                        )
                    )
                else:
                    raise ValueError(f"Unknown column rule type '{rtype}' on {table_name}.{col_name}")

        # 2. Table-level (cross-column) accuracy rules
        for rule in table_cfg.get("table_rules", []):
            rtype = rule["type"]
            threshold = float(rule.get("threshold", 100.0))

            if rtype == "accuracy_sql":
                results.append(
                    check_accuracy_sql_rule(
                        engine,
                        table_name=table_name,
                        rule_name=rule["rule_name"],
                        valid_sql_predicate=rule["predicate"],
                        required_columns=rule.get("required_columns"),
                        schema=schema,
                        threshold=threshold,
                    )
                )
            else:
                raise ValueError(f"Unknown table rule type '{rtype}' on {table_name}")

    return results


def export_results(results: list[DQResult], out_path: str, fmt: Optional[str] = None) -> Path:
    """Export DQResult list to CSV or JSON."""
    if not results:
        raise ValueError("No results to export.")

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    export_fmt = (fmt or path.suffix.lstrip(".")).lower()
    timestamp = datetime.now(timezone.utc).isoformat()

    records = [
        {
            "executed_at": timestamp,
            "status": "PASS" if r.passed else "FAIL",
            "dimension": r.dimension,
            "check_name": r.check_name,
            "table_column": f"{r.table}.{r.column}",
            "table": r.table,
            "column": r.column,
            "total_rows": r.total_rows,
            "valid_rows": r.valid_rows,
            "failed_rows": r.failed_rows,
            "valid_pct": round(r.pass_rate, 2),
            "details": r.details,
        }
        for r in results
    ]

    if export_fmt == "csv":
        # utf-8-sig ensures Excel on Windows opens UTF-8 CSV cleanly
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)
    elif export_fmt == "json":
        with path.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
    else:
        raise ValueError(f"Unsupported export format '{export_fmt}'. Use 'csv' or 'json'.")

    return path