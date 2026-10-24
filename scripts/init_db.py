"""CLI script to initialize the SQLite database from CSV.

Prints data-quality summary and row counts.
Usage:
    python scripts/init_db.py
"""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CSV_DATA_PATH, DATABASE_PATH
from app.loader import load_csv_data


def main() -> None:
    print("=" * 60)
    print("AI BI ASSISTANT - DATABASE INITIALIZATION & AUDIT")
    print("=" * 60)
    print(f"Source CSV : {CSV_DATA_PATH}")
    print(f"Database   : {DATABASE_PATH}")
    print("-" * 60)

    try:
        summary = load_csv_data(CSV_DATA_PATH, DATABASE_PATH)
        print(f"Total rows processed : {summary['total_rows']}")
        print(f"Rows INCLUDED in BI  : {summary['included_rows']}")
        print(f"Rows EXCLUDED from BI: {summary['excluded_rows']}")
        print("-" * 60)
        print("EXCLUDED ROWS AUDIT TRAIL:")
        for ex in summary["exclusions"]:
            raw = ex["raw_row"]
            print(
                f" - {ex['transaction_id']:<8} | Reason: {ex['reason']:<20} | "
                f"Status: {raw.get('Status', ''):<10} | Qty: {raw.get('Quantity', ''):<3} | "
                f"Price: {raw.get('Unit_price', ''):<6}"
            )
        print("=" * 60)
        print("Database initialized successfully.")
    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
