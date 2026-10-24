"""Database connection and initialization module.

Provides separate writer and read-only connections. Read-only connections enforce
PRAGMA query_only = ON and file mode=ro to ensure the analytics layer cannot modify the DB.
"""
import sqlite3
from pathlib import Path
from typing import Union
from app.config import DATABASE_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sales (
    transaction_id TEXT PRIMARY KEY,
    order_date TEXT,
    order_month TEXT,
    product TEXT,
    category TEXT,
    region TEXT,
    sales_channel TEXT,
    quantity INTEGER,
    unit_price REAL,
    discount_amount REAL,
    status TEXT,
    line_revenue REAL,
    is_included INTEGER NOT NULL,
    exclusion_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_sales_order_month ON sales(order_month);
CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product);
CREATE INDEX IF NOT EXISTS idx_sales_region ON sales(region);
CREATE INDEX IF NOT EXISTS idx_sales_is_included ON sales(is_included);
"""


def get_writer_connection(db_path: Union[str, Path] = DATABASE_PATH) -> sqlite3.Connection:
    """Return a read-write SQLite connection. Used strictly by loader."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def get_readonly_connection(db_path: Union[str, Path] = DATABASE_PATH) -> sqlite3.Connection:
    """Return a strict read-only SQLite connection.
    
    Uses URI mode=ro and executes PRAGMA query_only = ON.
    """
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Database file does not exist at {path}")
    
    # Windows path URI handling
    uri_path = path.as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri_path, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON;")
    return conn


def init_schema(db_path: Union[str, Path] = DATABASE_PATH) -> None:
    """Initialize the SQLite tables and indexes."""
    with get_writer_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
