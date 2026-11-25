# connectors.py
from dataclasses import dataclass
from typing import Literal, Optional
from sqlalchemy import create_engine, Engine, select, literal
from sqlalchemy.engine import URL

DBType = Literal["oracle", "sqlserver", "mysql"]


@dataclass
class DBConfig:
    db_type: DBType
    host: str
    port: int
    user: str
    password: str
    database: Optional[str] = None      # Database name (MySQL / SQL Server)
    service_name: Optional[str] = None  # Service name (Oracle)
    odbc_driver: str = "ODBC Driver 18 for SQL Server"


def create_db_engine(config: DBConfig) -> Engine:
    """Create a SQLAlchemy Engine for Oracle, SQL Server, or MySQL."""
    if config.db_type == "oracle":
        if not config.service_name:
            raise ValueError("Oracle connections require 'service_name'.")
        url = URL.create(
            drivername="oracle+oracledb",
            username=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            query={"service_name": config.service_name},
        )

    elif config.db_type == "sqlserver":
        url = URL.create(
            drivername="mssql+pyodbc",
            username=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            database=config.database,
            query={
                "driver": config.odbc_driver,
                "Encrypt": "yes",
                "TrustServerCertificate": "yes",  # Useful for dev/self-signed certs
            },
        )

    elif config.db_type == "mysql":
        url = URL.create(
            drivername="mysql+pymysql",
            username=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            database=config.database,
            query={"charset": "utf8mb4"},
        )

    else:
        raise ValueError(f"Unsupported database type: {config.db_type}")

    return create_engine(url, pool_pre_ping=True)


def test_connection(engine: Engine) -> bool:
    """Verify database connectivity (SQLAlchemy auto-adds FROM DUAL on Oracle)."""
    try:
        with engine.connect() as conn:
            result = conn.execute(select(literal(1))).scalar()
            return result == 1
    except Exception as exc:
        print(f"Connection failed ({engine.dialect.name}): {exc}")
        return False