# main.py
import traceback
import argparse
import getpass
from sqlalchemy import inspect
import cmd
import shlex
from typing import Optional


from utils import connectors, checks
from utils.connectors import DBConfig, create_db_engine, test_connection
from utils.checks import (
    DQResult,
    check_completeness,
    check_validity_allowed_values,
    check_validity_range,
    check_validity_pattern,
    check_accuracy_sql_rule,
    format_results_table,
)


def _parse_columns(raw_cols: list[str]) -> list[str]:
    """Support both '--columns a b' and '--columns a,b'."""
    cols = []
    for item in raw_cols:
        cols.extend(c.strip() for c in item.split(",") if c.strip())
    return cols


def _safe_parse(parser: argparse.ArgumentParser, arg_str: str) -> Optional[argparse.Namespace]:
    """Parse CLI args inside the REPL without exiting the shell on --help or typos."""
    try:
        tokens = shlex.split(arg_str)
        return parser.parse_args(tokens)
    except SystemExit:
        return None


class DQShell(cmd.Cmd):
    intro = (
        "\n=== Data Quality Interactive CLI ===\n"
        "Type 'help' or '?' to list commands. Start with 'connect ...'\n"
    )
    prompt = "dq> "

    def __init__(self):
        super().__init__()
        self.engine: Optional[Engine] = None
        self.config: Optional[DBConfig] = None

    def _require_connection(self) -> bool:
        if self.engine is None:
            print("Not connected. Run 'connect --db-type ...' first.")
            return False
        return True

    # ------------------------------------------------------------------
    # CONNECTION COMMANDS
    # ------------------------------------------------------------------
    def do_connect(self, arg: str):
        """Connect to a database and keep the connection pool open."""
        parser = argparse.ArgumentParser(prog="connect")
        parser.add_argument("--db-type", required=True, choices=["oracle", "sqlserver", "mysql"])
        parser.add_argument("--host", required=True)
        parser.add_argument("--port", required=True, type=int)
        parser.add_argument("-u", "--username", "--user", dest="username", required=True)
        parser.add_argument("-p", "--password", default=None)
        parser.add_argument("-d", "--database", default=None)
        parser.add_argument("--service-name", default=None)
        parser.add_argument("--odbc-driver", default="ODBC Driver 18 for SQL Server")

        args = _safe_parse(parser, arg)
        if not args:
            return

        if args.db_type == "oracle" and not args.service_name:
            print("Error: --service-name is required for Oracle.")
            return

        password = args.password if args.password is not None else getpass.getpass("Password: ")

        cfg = DBConfig(
            db_type=args.db_type,
            host=args.host,
            port=args.port,
            user=args.username,
            password=password,
            database=args.database,
            service_name=args.service_name,
            odbc_driver=args.odbc_driver,
        )

        new_engine = create_db_engine(cfg)
        if not test_connection(new_engine):
            new_engine.dispose()
            print("Failed to connect. Previous connection (if any) was kept.")
            return

        if self.engine is not None:
            self.engine.dispose()

        self.engine = new_engine
        self.config = cfg
        db_label = cfg.database or cfg.service_name or cfg.host
        self.prompt = f"dq ({cfg.db_type}:{db_label})> "
        print(f"Connected! Server version: {self.engine.dialect.server_version_info}")

    def do_status(self, arg: str):
        """Show current active database connection."""
        if not self._require_connection():
            return
        print(
            f"Connected to {self.config.db_type} @ {self.config.host}:{self.config.port} "
            f"(db/service: {self.config.database or self.config.service_name})"
        )

    def do_tables(self, arg: str):
        """List tables in the connected database/schema. Usage: tables [schema_name]"""
        if not self._require_connection():
            return
        schema = arg.strip() or None
        tables = inspect(self.engine).get_table_names(schema=schema)
        print(f"Tables ({len(tables)}): {tables}")

    def do_disconnect(self, arg: str):
        """Close the active database connection pool."""
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
            self.config = None
            self.prompt = "dq> "
            print("Disconnected.")
        else:
            print("No active connection.")

    # ------------------------------------------------------------------
    # DATA QUALITY CHECK COMMAND
    # ------------------------------------------------------------------
    def do_check(self, arg: str):
        """
        Run DQ checks against the open connection.
        Subcommands: completeness | validity | accuracy
        Run 'check completeness --help' (etc.) for options.
        """
        if not self._require_connection():
            return

        parser = argparse.ArgumentParser(prog="check")
        subparsers = parser.add_subparsers(dest="dimension", required=True)

        # 1. completeness
        p_comp = subparsers.add_parser("completeness", help="Check for NULL / blank values")
        p_comp.add_argument("-t", "--table", required=True, help="Table name")
        p_comp.add_argument("-c", "--columns", nargs="+", required=True, help="One or more columns")
        p_comp.add_argument("--schema", default=None, help="Optional schema name")
        p_comp.add_argument("--blank", action="store_true", help="Also fail empty/whitespace strings")
        p_comp.add_argument("--threshold", type=float, default=100.0, help="Pass rate threshold %%")

        # 2. validity
        p_val = subparsers.add_parser("validity", help="Check domain, range, or LIKE pattern")
        p_val.add_argument("-t", "--table", required=True, help="Table name")
        p_val.add_argument("-c", "--columns", nargs="+", required=True, help="One or more columns")
        p_val.add_argument("--schema", default=None, help="Optional schema name")
        p_val.add_argument("--allowed", nargs="+", default=None, help="Allowed values list")
        p_val.add_argument("--min", dest="min_val", type=float, default=None, help="Minimum value")
        p_val.add_argument("--max", dest="max_val", type=float, default=None, help="Maximum value")
        p_val.add_argument("--pattern", default=None, help="SQL LIKE pattern (e.g. '%%@%%.%%')")
        p_val.add_argument("--threshold", type=float, default=100.0, help="Pass rate threshold %%")

        # 3. accuracy
        p_acc = subparsers.add_parser("accuracy", help="Check cross-column SQL business rule")
        p_acc.add_argument("-t", "--table", required=True, help="Table name")
        p_acc.add_argument("-c", "--columns", nargs="+", default=None, help="Required non-null columns")
        p_acc.add_argument("--schema", default=None, help="Optional schema name")
        p_acc.add_argument("--rule-name", required=True, help="Name of the accuracy rule")
        p_acc.add_argument("--predicate", required=True, help="SQL expression that must be TRUE")
        p_acc.add_argument("--threshold", type=float, default=100.0, help="Pass rate threshold %%")

        args = _safe_parse(parser, arg)
        if not args:
            return

        results: list[DQResult] = []
        try:
            if args.dimension == "completeness":
                cols = _parse_columns(args.columns)
                for col in cols:
                    results.append(
                        check_completeness(
                            self.engine,
                            table_name=args.table,
                            col_name=col,
                            schema=args.schema,
                            check_blank_strings=args.blank,
                            threshold=args.threshold,
                        )
                    )

            elif args.dimension == "validity":
                cols = _parse_columns(args.columns)
                has_rule = (
                    args.allowed is not None
                    or args.min_val is not None
                    or args.max_val is not None
                    or args.pattern is not None
                )
                if not has_rule:
                    print("Error: Specify at least one of --allowed, --min, --max, or --pattern.")
                    return

                for col in cols:
                    if args.allowed is not None:
                        results.append(
                            check_validity_allowed_values(
                                self.engine,
                                table_name=args.table,
                                col_name=col,
                                allowed_values=args.allowed,
                                schema=args.schema,
                                threshold=args.threshold,
                            )
                        )
                    if args.min_val is not None or args.max_val is not None:
                        results.append(
                            check_validity_range(
                                self.engine,
                                table_name=args.table,
                                col_name=col,
                                min_val=args.min_val,
                                max_val=args.max_val,
                                schema=args.schema,
                                threshold=args.threshold,
                            )
                        )
                    if args.pattern is not None:
                        results.append(
                            check_validity_pattern(
                                self.engine,
                                table_name=args.table,
                                col_name=col,
                                like_pattern=args.pattern,
                                schema=args.schema,
                                threshold=args.threshold,
                            )
                        )

            elif args.dimension == "accuracy":
                cols = _parse_columns(args.columns) if args.columns else None
                results.append(
                    check_accuracy_sql_rule(
                        self.engine,
                        table_name=args.table,
                        rule_name=args.rule_name,
                        valid_sql_predicate=args.predicate,
                        required_columns=cols,
                        schema=args.schema,
                        threshold=args.threshold,
                    )
                )

            print("\n" + format_results_table(results) + "\n")

        except Exception as exc:
            print(f"Check execution error: {exc}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # EXIT
    # ------------------------------------------------------------------
    def do_exit(self, arg: str):
        """Disconnect and exit the CLI."""
        self.do_disconnect("")
        return True

    def do_quit(self, arg: str):
        """Alias for exit."""
        return self.do_exit(arg)


if __name__ == "__main__":
    DQShell().cmdloop()