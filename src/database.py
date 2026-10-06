"""
src/database.py — Database connection and helper functions.

Provides:
    get_engine()         — SQLAlchemy engine (singleton-ish per URL).
    get_connection()     — Context-manager yielding a connection.
    execute_query()      — Run arbitrary parameterised SQL.
    insert_dataframe()   — Bulk-load a Pandas DataFrame into a table.
    init_schema()        — Run sql/schema.sql to create tables.

Uses parameterised queries exclusively to prevent SQL injection.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Connection

from src.config import Config, get_config
from src.logging_config import get_logger

logger = get_logger(__name__)

# Module-level engine cache
_engine_cache: dict[str, Engine] = {}


def get_engine(config: Optional[Config] = None) -> Engine:
    """Return a SQLAlchemy engine, creating one if necessary."""
    cfg = config or get_config()
    url = cfg.database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")

    if url not in _engine_cache:
        logger.info("Creating database engine")
        _engine_cache[url] = create_engine(
            url,
            pool_pre_ping=True,      # reconnect on stale connections
            pool_size=5,
            max_overflow=10,
        )
    return _engine_cache[url]


@contextmanager
def get_connection(config: Optional[Config] = None) -> Generator[Connection, None, None]:
    """Context-manager that yields a database connection and commits on success."""
    engine = get_engine(config)
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_query(
    sql: str,
    params: Optional[dict[str, Any]] = None,
    config: Optional[Config] = None,
) -> list[dict[str, Any]]:
    """
    Execute a parameterised SQL statement and return rows as dicts.

    For INSERT/UPDATE/DELETE queries the returned list will be empty
    unless the query includes a RETURNING clause.
    """
    with get_connection(config) as conn:
        result = conn.execute(text(sql), params or {})
        if result.returns_rows:
            return [dict(row._mapping) for row in result]
        return []


def insert_dataframe(
    df: pd.DataFrame,
    table_name: str,
    if_exists: str = "replace",
    config: Optional[Config] = None,
) -> int:
    """
    Bulk-insert a DataFrame into *table_name*.

    Args:
        if_exists: 'replace' drops & recreates the table; 'append' adds rows.

    Returns the number of rows inserted.
    """
    engine = get_engine(config)
    row_count = len(df)
    logger.info("Inserting %d rows into '%s' (if_exists=%s)", row_count, table_name, if_exists)
    df.to_sql(table_name, engine, if_exists=if_exists, index=False, method="multi", chunksize=500)
    logger.info("Insert complete: %d rows", row_count)
    return row_count


def init_schema(config: Optional[Config] = None) -> None:
    """Run sql/schema.sql to create all required tables and indexes."""
    schema_path = os.path.join(os.path.dirname(__file__), "..", "sql", "schema.sql")
    schema_path = os.path.abspath(schema_path)

    if not os.path.isfile(schema_path):
        logger.error("Schema file not found: %s", schema_path)
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as fh:
        sql_content = fh.read()

    with get_connection(config) as conn:
        # Execute each statement separately (split on semicolons)
        for statement in sql_content.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
    logger.info("Database schema initialised from %s", schema_path)
