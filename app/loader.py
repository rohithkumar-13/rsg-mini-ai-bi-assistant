"""CSV data loader and validator.

Loads sales data from CSV into SQLite table `sales` idempotently while enforcing
business rules and maintaining an audit log of excluded records.
"""
import csv
import logging
from pathlib import Path
from typing import Any, Dict, List, Union
from app.config import CSV_DATA_PATH, DATABASE_PATH
from app.database import get_writer_connection, init_schema
from app.rules import (
    EXCLUSION_DUPLICATE_ID,
    validate_and_parse_row,
)

logger = logging.getLogger(__name__)


def load_csv_data(
    csv_path: Union[str, Path] = CSV_DATA_PATH,
    db_path: Union[str, Path] = DATABASE_PATH,
) -> Dict[str, Any]:
    """Load and validate CSV data into the SQLite database.
    
    Idempotent operation: re-running replaces existing rows with the fresh CSV content.
    Returns summary statistics including included and excluded counts.
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"Source CSV not found at {csv_file}")

    # Ensure DB schema is ready
    init_schema(db_path)

    rows_to_insert: List[Dict[str, Any]] = []
    seen_transaction_ids = set()
    included_count = 0
    excluded_count = 0
    exclusions_list: List[Dict[str, Any]] = []

    with open(csv_file, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV file at {csv_file} is empty or has no header.")

        for row in reader:
            tid = str(row.get("Transaction_Id", "")).strip()
            
            # Check for duplicate ID
            if tid in seen_transaction_ids:
                is_included = False
                exclusion_reason = EXCLUSION_DUPLICATE_ID
                _, _, parsed = validate_and_parse_row(row)
                parsed["is_included"] = False
                parsed["exclusion_reason"] = exclusion_reason
            else:
                seen_transaction_ids.add(tid)
                is_included, exclusion_reason, parsed = validate_and_parse_row(row)

            if is_included:
                included_count += 1
            else:
                excluded_count += 1
                exclusions_list.append({
                    "transaction_id": tid,
                    "reason": exclusion_reason,
                    "raw_row": row,
                })

            rows_to_insert.append(parsed)

    # Idempotent write to SQLite using transaction
    insert_sql = """
    INSERT OR REPLACE INTO sales (
        transaction_id, order_date, order_month, product, category,
        region, sales_channel, quantity, unit_price, discount_amount,
        status, line_revenue, is_included, exclusion_reason
    ) VALUES (
        :transaction_id, :order_date, :order_month, :product, :category,
        :region, :sales_channel, :quantity, :unit_price, :discount_amount,
        :status, :line_revenue, :is_included, :exclusion_reason
    );
    """

    with get_writer_connection(db_path) as conn:
        cursor = conn.cursor()
        # Clear table for strict idempotence when re-loading source data
        cursor.execute("DELETE FROM sales;")
        cursor.executemany(insert_sql, rows_to_insert)
        conn.commit()

    logger.info(
        f"Loaded {len(rows_to_insert)} total rows into SQLite: "
        f"{included_count} included, {excluded_count} excluded."
    )

    return {
        "total_rows": len(rows_to_insert),
        "included_rows": included_count,
        "excluded_rows": excluded_count,
        "exclusions": exclusions_list,
    }
