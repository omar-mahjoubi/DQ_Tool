# main.py
from sqlalchemy import inspect, text
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils import connectors, checks
from utils.connectors import DBConfig, create_db_engine, test_connection
from utils.checks import (
    check_completeness,
    check_validity_allowed_values,
    check_validity_range,
    check_accuracy_sql_rule,
)


def main():
    # 1. Configure your local MySQL connection
    mysql_cfg = DBConfig(
        db_type="mysql",
        host="127.0.0.1",               # Use 127.0.0.1 (or "localhost")
        port=3306,                      # Default MySQL port
        user="root",                    # Your MySQL username
        password="root", # Your MySQL password
        database="sakila",  # An existing schema/database in MySQL
    )

    # 2. Create engine & test connection
    engine = create_db_engine(mysql_cfg)

    print("Testing connection to local MySQL...")
    if not test_connection(engine):
        raise SystemExit("Connection failed. Check host, port, credentials, and MySQL service.")

    print("Connected successfully!")

    # 3. Fetch MySQL version & list tables in your database
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar()
        print(f"MySQL Version: {version}")

    tables = inspect(engine).get_table_names()
    print(f"Tables found in '{mysql_cfg.database}': {tables}")

    # 4. (Optional) Uncomment and replace with one of your actual tables/columns to run DQ tests
    # results = [
    #     check_completeness(engine, table_name="users", col_name="email", check_blank_strings=True),
    #     check_validity_allowed_values(engine, table_name="orders", col_name="status", allowed_values=["PENDING", "PAID"]),
    #     check_validity_range(engine, table_name="products", col_name="price", min_val=0),
    #     check_accuracy_sql_rule(
    #         engine,
    #         table_name="order_items",
    #         rule_name="total_check",
    #         valid_sql_predicate="ABS(total - (qty * price)) < 0.01",
    #     ),
    # ]
    # for res in results:
    #     print(res.summary())


if __name__ == "__main__":
    main()