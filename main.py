# main.py
import argparse
import getpass
from sqlalchemy import inspect



from utils import connectors, checks
from utils.connectors import DBConfig, create_db_engine, test_connection
from utils.checks import (
    check_completeness,
    check_validity_allowed_values,
    check_validity_range,
    check_accuracy_sql_rule,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Data Quality Tool - Test DB connection and run DQ checks."
    )
    parser.add_argument(
        "--db-type",
        required=True,
        choices=["oracle", "sqlserver", "mysql"],
        help="Target database type.",
    )
    parser.add_argument("--host", required=True, help="Database host or IP.")
    parser.add_argument("--port", required=True, type=int, help="Database port.")
    parser.add_argument(
        "-u", "--username", "--user",
        dest="username",
        required=True,
        help="Database username.",
    )
    parser.add_argument(
        "-p", "--password",
        required=False,
        default=None,
        help="Database password (if omitted, you will be prompted securely).",
    )
    parser.add_argument(
        "-d", "--database",
        default=None,
        help="Database/schema name (used for MySQL and SQL Server).",
    )
    parser.add_argument(
        "--service-name",
        default=None,
        help="Oracle service name (required when --db-type is 'oracle').",
    )
    parser.add_argument(
        "--odbc-driver",
        default="ODBC Driver 18 for SQL Server",
        help="ODBC driver name for SQL Server.",
    )

    args = parser.parse_args()

    if args.db_type == "oracle" and not args.service_name:
        parser.error("--service-name is required when --db-type is 'oracle'.")

    if args.password is None:
        args.password = getpass.getpass("Database password: ")

    return args


def main():
    args = parse_args()

    config = DBConfig(
        db_type=args.db_type,
        host=args.host,
        port=args.port,
        user=args.username,
        password=args.password,
        database=args.database,
        service_name=args.service_name,
        odbc_driver=args.odbc_driver,
    )

    engine = create_db_engine(config)

    print(f"Testing connection to {args.db_type} at {args.host}:{args.port}...")
    if not test_connection(engine):
        raise SystemExit("Connection failed.")

    version = engine.dialect.server_version_info
    print(f"Connected successfully! Dialect={engine.dialect.name}, Server Version={version}")

    inspector = inspect(engine)
    if args.database or args.db_type == "oracle":
        tables = inspector.get_table_names()
        print(f"Tables found: {tables}")
    else:
        schemas = inspector.get_schema_names()
        print(f"No --database specified. Available databases/schemas: {schemas}")

    # Example: run checks once you know your table/column names
    # results = [
    #     check_completeness(engine, table_name="users", col_name="email", check_blank_strings=True),
    #     check_validity_range(engine, table_name="products", col_name="price", min_val=0),
    #     check_accuracy_sql_rule(
    #         engine,
    #         table_name="order_items",
    #         rule_name="line_total_math",
    #         valid_sql_predicate="ABS(total_amount - (quantity * unit_price)) < 0.01",
    #     ),
    # ]
    # for res in results:
    #     print(res.summary())


if __name__ == "__main__":
    main()