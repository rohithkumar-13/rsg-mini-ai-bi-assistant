"""Tests for SQL defense-in-depth guard and read-only connection enforcement."""
import sqlite3
from pathlib import Path
import pytest

from app.database import get_readonly_connection
from app.sql_guard import SQLSecurityError, validate_select_only


def test_sql_guard_accepts_valid_select():
    """Assert valid parameterized SELECT queries pass validation."""
    valid_queries = [
        "SELECT * FROM sales WHERE is_included = 1",
        "SELECT product, SUM(line_revenue) FROM sales GROUP BY product ORDER BY 2 DESC LIMIT 1;",
        "SELECT order_month, SUM(line_revenue) FROM sales WHERE order_month = ? GROUP BY order_month",
    ]
    for q in valid_queries:
        assert validate_select_only(q) is True


@pytest.mark.parametrize(
    "forbidden_sql",
    [
        "DROP TABLE sales;",
        "DELETE FROM sales WHERE 1=1;",
        "UPDATE sales SET line_revenue = 0;",
        "INSERT INTO sales VALUES ('T', '01-01-2026', '2026-01', 'P', 'C', 'R', 'S', 1, 10, 0, 'Completed', 10, 1, NULL);",
        "ATTACH DATABASE 'evil.db' AS evil;",
        "PRAGMA query_only = OFF;",
        "ALTER TABLE sales ADD COLUMN evil TEXT;",
        "CREATE TABLE evil (id INT);",
    ],
)
def test_sql_guard_rejects_forbidden_keywords(forbidden_sql: str):
    """Assert any DDL/DML mutation keyword raises SQLSecurityError."""
    with pytest.raises(SQLSecurityError, match="Forbidden SQL keyword|Query must begin with SELECT"):
        validate_select_only(forbidden_sql)


def test_sql_guard_rejects_stacked_statements():
    """Assert semicolon statement chaining is rejected."""
    stacked_sql = "SELECT * FROM sales; DROP TABLE sales;"
    with pytest.raises(SQLSecurityError, match="Stacked statements / multiple queries are strictly forbidden"):
        validate_select_only(stacked_sql)


def test_sql_guard_rejects_sql_comments():
    """Assert SQL comments (-- and /* */) are rejected."""
    comment_sqls = [
        "SELECT * FROM sales -- bypass check",
        "SELECT * FROM sales /* inline block */ WHERE 1=1",
    ]
    for q in comment_sqls:
        with pytest.raises(SQLSecurityError, match="SQL comments are strictly forbidden"):
            validate_select_only(q)


def test_readonly_connection_enforces_write_prohibition(loaded_temp_db: Path):
    """Assert SQLite read-only connection strictly prevents data mutation at the engine level."""
    with get_readonly_connection(loaded_temp_db) as conn:
        cursor = conn.cursor()
        # Even if a malicious SQL bypassed python filters, SQLite engine rejects write
        with pytest.raises(sqlite3.OperationalError, match="attempt to write a readonly database"):
            cursor.execute("DELETE FROM sales;")
