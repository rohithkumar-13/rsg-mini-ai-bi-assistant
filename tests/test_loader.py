"""Tests for CSV data loading and validation rules."""
import csv
from pathlib import Path
import pytest

from app.config import CSV_DATA_PATH
from app.database import get_readonly_connection
from app.loader import load_csv_data
from app.rules import (
    EXCLUSION_DUPLICATE_ID,
    EXCLUSION_INVALID_DATE,
    EXCLUSION_INVALID_DISCOUNT,
    EXCLUSION_INVALID_QUANTITY,
    EXCLUSION_MISSING_PRICE,
    EXCLUSION_NEGATIVE_PRICE,
    EXCLUSION_RETURNED,
    EXCLUSION_ZERO_QUANTITY,
)


def test_official_csv_loading_and_counts(temp_db_path: Path):
    """Verify official CSV loads 51 rows: 48 included, 3 excluded with exact reasons."""
    summary = load_csv_data(csv_path=CSV_DATA_PATH, db_path=temp_db_path)

    assert summary["total_rows"] == 51
    assert summary["included_rows"] == 48
    assert summary["excluded_rows"] == 3

    exclusions = {e["transaction_id"]: e["reason"] for e in summary["exclusions"]}
    assert exclusions.get("TXN0033") == EXCLUSION_RETURNED
    assert exclusions.get("TXN0034") == EXCLUSION_ZERO_QUANTITY
    assert exclusions.get("TXN0051") == EXCLUSION_MISSING_PRICE


def test_official_csv_source_values_unaltered(temp_db_path: Path):
    """Verify that original source values are preserved without alteration or price imputation."""
    load_csv_data(csv_path=CSV_DATA_PATH, db_path=temp_db_path)

    with get_readonly_connection(temp_db_path) as conn:
        cursor = conn.cursor()

        # Check TXN0033 (Returned)
        cursor.execute("SELECT status, is_included, exclusion_reason FROM sales WHERE transaction_id = 'TXN0033'")
        row33 = cursor.fetchone()
        assert row33["status"] == "Returned"
        assert row33["is_included"] == 0
        assert row33["exclusion_reason"] == EXCLUSION_RETURNED

        # Check TXN0034 (Quantity = 0, preserves unit_price 900.0 and discount 0)
        cursor.execute("SELECT quantity, unit_price, discount_amount, is_included, exclusion_reason FROM sales WHERE transaction_id = 'TXN0034'")
        row34 = cursor.fetchone()
        assert row34["quantity"] == 0
        assert row34["unit_price"] == 900.0
        assert row34["discount_amount"] == 0
        assert row34["is_included"] == 0
        assert row34["exclusion_reason"] == EXCLUSION_ZERO_QUANTITY

        # Check TXN0051 (Missing Unit_price - remains NULL/None, preserves discount 0)
        cursor.execute("SELECT quantity, unit_price, discount_amount, is_included, exclusion_reason FROM sales WHERE transaction_id = 'TXN0051'")
        row51 = cursor.fetchone()
        assert row51["unit_price"] is None
        assert row51["discount_amount"] == 0
        assert row51["is_included"] == 0
        assert row51["exclusion_reason"] == EXCLUSION_MISSING_PRICE


def test_excluded_rows_keep_parseable_source_values(temp_db_path: Path):
    """Assert that TXN0034 keeps unit_price 900.0 and discount 0, and TXN0051 keeps discount 0 with unit_price NULL."""
    load_csv_data(csv_path=CSV_DATA_PATH, db_path=temp_db_path)

    with get_readonly_connection(temp_db_path) as conn:
        cursor = conn.cursor()

        # TXN0034: Zero quantity failure, but keeps unit_price 900.0 and discount 0
        cursor.execute(
            "SELECT unit_price, discount_amount, quantity, is_included, exclusion_reason "
            "FROM sales WHERE transaction_id = 'TXN0034'"
        )
        row34 = cursor.fetchone()
        assert row34["unit_price"] == 900.0
        assert row34["discount_amount"] == 0
        assert row34["quantity"] == 0
        assert row34["is_included"] == 0
        assert row34["exclusion_reason"] == EXCLUSION_ZERO_QUANTITY

        # TXN0051: Missing unit_price (NULL), but keeps discount 0
        cursor.execute(
            "SELECT unit_price, discount_amount, quantity, is_included, exclusion_reason "
            "FROM sales WHERE transaction_id = 'TXN0051'"
        )
        row51 = cursor.fetchone()
        assert row51["unit_price"] is None
        assert row51["discount_amount"] == 0
        assert row51["quantity"] == 5
        assert row51["is_included"] == 0
        assert row51["exclusion_reason"] == EXCLUSION_MISSING_PRICE



def test_loader_idempotence(temp_db_path: Path):
    """Verify re-running the loader does not duplicate rows or alter counts."""
    summary1 = load_csv_data(csv_path=CSV_DATA_PATH, db_path=temp_db_path)
    summary2 = load_csv_data(csv_path=CSV_DATA_PATH, db_path=temp_db_path)

    assert summary1["total_rows"] == summary2["total_rows"] == 51
    assert summary1["included_rows"] == summary2["included_rows"] == 48

    with get_readonly_connection(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sales")
        count = cursor.fetchone()[0]
        assert count == 51


def _write_csv(path: Path, rows: list):
    headers = [
        "Transaction_Id", "Order_date", "Product", "Category", "Region",
        "Sales_channel", "Quantity", "Unit_price", "Discount_amount", "Status"
    ]
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_synthetic_edge_case_bad_date(tmp_path: Path):
    """Verify invalid date string marks row excluded with invalid_date."""
    csv_file = tmp_path / "bad_date.csv"
    db_file = tmp_path / "test.db"
    _write_csv(csv_file, [{
        "Transaction_Id": "T9901",
        "Order_date": "2026/01/15",  # Invalid format (expects DD-MM-YYYY)
        "Product": "Mouse",
        "Category": "Accessories",
        "Region": "North",
        "Sales_channel": "Online",
        "Quantity": "2",
        "Unit_price": "500",
        "Discount_amount": "0",
        "Status": "Completed",
    }])
    summary = load_csv_data(csv_path=csv_file, db_path=db_file)
    assert summary["included_rows"] == 0
    assert summary["exclusions"][0]["reason"] == EXCLUSION_INVALID_DATE


def test_synthetic_edge_case_negative_and_zero_values(tmp_path: Path):
    """Verify negative quantity and negative unit price are properly excluded."""
    csv_file = tmp_path / "negatives.csv"
    db_file = tmp_path / "test.db"
    _write_csv(csv_file, [
        {
            "Transaction_Id": "T9902",
            "Order_date": "15-01-2026",
            "Product": "Mouse",
            "Category": "Accessories",
            "Region": "North",
            "Sales_channel": "Online",
            "Quantity": "-5",
            "Unit_price": "500",
            "Discount_amount": "0",
            "Status": "Completed",
        },
        {
            "Transaction_Id": "T9903",
            "Order_date": "16-01-2026",
            "Product": "Keyboard",
            "Category": "Accessories",
            "Region": "South",
            "Sales_channel": "Retail",
            "Quantity": "3",
            "Unit_price": "-100",
            "Discount_amount": "0",
            "Status": "Completed",
        },
    ])
    summary = load_csv_data(csv_path=csv_file, db_path=db_file)
    assert summary["included_rows"] == 0
    reasons = {e["transaction_id"]: e["reason"] for e in summary["exclusions"]}
    assert reasons["T9902"] == EXCLUSION_INVALID_QUANTITY
    assert reasons["T9903"] == EXCLUSION_NEGATIVE_PRICE


def test_synthetic_edge_case_discount_greater_than_total(tmp_path: Path):
    """Verify discount > gross line total is excluded as invalid_discount."""
    csv_file = tmp_path / "bad_discount.csv"
    db_file = tmp_path / "test.db"
    _write_csv(csv_file, [{
        "Transaction_Id": "T9904",
        "Order_date": "15-01-2026",
        "Product": "Mouse",
        "Category": "Accessories",
        "Region": "North",
        "Sales_channel": "Online",
        "Quantity": "2",
        "Unit_price": "500",  # Total gross = 1000
        "Discount_amount": "1500",  # Invalid: 1500 > 1000
        "Status": "Completed",
    }])
    summary = load_csv_data(csv_path=csv_file, db_path=db_file)
    assert summary["included_rows"] == 0
    assert summary["exclusions"][0]["reason"] == EXCLUSION_INVALID_DISCOUNT


def test_synthetic_edge_case_duplicate_transaction_id(tmp_path: Path):
    """Verify duplicate Transaction_Id is flagged as duplicate_transaction_id."""
    csv_file = tmp_path / "dup_id.csv"
    db_file = tmp_path / "test.db"
    _write_csv(csv_file, [
        {
            "Transaction_Id": "T_DUP",
            "Order_date": "15-01-2026",
            "Product": "Mouse",
            "Category": "Accessories",
            "Region": "North",
            "Sales_channel": "Online",
            "Quantity": "2",
            "Unit_price": "500",
            "Discount_amount": "0",
            "Status": "Completed",
        },
        {
            "Transaction_Id": "T_DUP",
            "Order_date": "16-01-2026",
            "Product": "Keyboard",
            "Category": "Accessories",
            "Region": "South",
            "Sales_channel": "Retail",
            "Quantity": "1",
            "Unit_price": "800",
            "Discount_amount": "0",
            "Status": "Completed",
        },
    ])
    summary = load_csv_data(csv_path=csv_file, db_path=db_file)
    assert summary["included_rows"] == 1
    assert summary["excluded_rows"] == 1
    assert summary["exclusions"][0]["reason"] == EXCLUSION_DUPLICATE_ID


def test_synthetic_edge_case_empty_file(tmp_path: Path):
    """Verify loading empty CSV raises a clear descriptive ValueError."""
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")
    db_file = tmp_path / "test.db"
    with pytest.raises(ValueError, match="empty or has no header"):
        load_csv_data(csv_path=empty_csv, db_path=db_file)
