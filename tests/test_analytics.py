"""Tests for deterministic analytics calculations and edge cases."""
from pathlib import Path
import pytest

from app import analytics
from app.database import get_writer_connection


def test_total_revenue(loaded_temp_db: Path):
    """Assert total revenue equals 1,439,200 across 48 included rows."""
    res = analytics.get_total_revenue(loaded_temp_db)
    assert res["result"]["total_revenue"] == 1439200.0
    assert res["result"]["transaction_count"] == 48
    assert "1,439,200" in res["answer"]


def test_top_product_by_revenue(loaded_temp_db: Path):
    """Assert Monitor is top product with 473,000."""
    res = analytics.get_top_product_by_revenue(loaded_temp_db)
    assert res["result"]["top_product"] == "Monitor"
    assert res["result"]["revenue"] == 473000.0
    assert "Monitor" in res["answer"]
    assert "473,000" in res["answer"]


def test_top_region_by_sales(loaded_temp_db: Path):
    """Assert South is top region with 411,200."""
    res = analytics.get_top_region_by_sales(loaded_temp_db)
    assert res["result"]["top_region"] == "South"
    assert res["result"]["revenue"] == 411200.0
    assert "South" in res["answer"]
    assert "411,200" in res["answer"]


def test_monthly_revenue_trend(loaded_temp_db: Path):
    """Assert monthly revenue trajectory and peak in May at 318,500."""
    res = analytics.get_monthly_revenue_trend(loaded_temp_db)
    assert res["result"]["peak_month"] == "2026-05"
    assert res["result"]["peak_revenue"] == 318500.0
    assert res["result"]["start_month"] == "2026-01"
    assert res["result"]["end_month"] == "2026-06"

    # Verify monthly numbers in supporting data
    data_by_month = {r["order_month"]: r["monthly_revenue"] for r in res["supporting_data"]}
    expected_months = {
        "2026-01": 210250.0,
        "2026-02": 234600.0,
        "2026-03": 223900.0,
        "2026-04": 240700.0,
        "2026-05": 318500.0,
        "2026-06": 211250.0,
    }
    assert data_by_month == expected_months


def test_revenue_change_between_jan_and_feb(loaded_temp_db: Path):
    """Assert Jan -> Feb change equals +24,350 (+11.58%)."""
    res = analytics.get_revenue_change_between_months("2026-01", "2026-02", loaded_temp_db)
    assert res["result"]["revenue_a"] == 210250.0
    assert res["result"]["revenue_b"] == 234600.0
    assert res["result"]["absolute_change"] == 24350.0
    assert res["result"]["percentage_change"] == 11.58
    assert "+24,350" in res["answer"]
    assert "+11.58%" in res["answer"]


def test_revenue_change_same_month(loaded_temp_db: Path):
    """Assert comparing the same month yields 0 delta and 0.0% change."""
    res = analytics.get_revenue_change_between_months("2026-03", "2026-03", loaded_temp_db)
    assert res["result"]["absolute_change"] == 0.0
    assert res["result"]["percentage_change"] == 0.0


def test_revenue_change_unknown_month(loaded_temp_db: Path):
    """Assert querying non-existent months returns informative message without raising."""
    res = analytics.get_revenue_change_between_months("2026-01", "2026-11", loaded_temp_db)
    assert "error" in res
    assert "2026-11" in res["answer"]


def test_revenue_change_zero_base_revenue(loaded_temp_db: Path):
    """Assert base month with 0 revenue does not crash with ZeroDivisionError and returns null pct."""
    # Insert a synthetic month with 0 revenue
    with get_writer_connection(loaded_temp_db) as conn:
        conn.execute(
            """INSERT INTO sales (transaction_id, order_date, order_month, product, category,
               region, sales_channel, quantity, unit_price, discount_amount, status,
               line_revenue, is_included, exclusion_reason)
               VALUES ('T_ZERO', '01-09-2026', '2026-09', 'Promo', 'Free',
               'North', 'Online', 1, 0.0, 0.0, 'Completed', 0.0, 1, NULL);"""
        )
        conn.commit()

    res = analytics.get_revenue_change_between_months("2026-09", "2026-01", loaded_temp_db)
    assert res["result"]["revenue_a"] == 0.0
    assert res["result"]["revenue_b"] == 210250.0
    assert res["result"]["absolute_change"] == 210250.0
    assert res["result"]["percentage_change"] is None  # Safe division!


def test_deterministic_tie_breaker(tmp_path: Path):
    """Assert deterministic alphabetical tie-breaker when two products have identical revenue."""
    db_file = tmp_path / "tie.db"
    from app.database import init_schema
    init_schema(db_file)
    with get_writer_connection(db_file) as conn:
        # Product B and Product A both have 1000 revenue. Product A should win by alphabetical ASC tie-break.
        conn.execute(
            """INSERT INTO sales (transaction_id, order_date, order_month, product, category,
               region, sales_channel, quantity, unit_price, discount_amount, status,
               line_revenue, is_included, exclusion_reason)
               VALUES 
               ('T1', '01-01-2026', '2026-01', 'Zeta', 'Cat', 'North', 'Online', 1, 1000, 0, 'Completed', 1000, 1, NULL),
               ('T2', '01-01-2026', '2026-01', 'Alpha', 'Cat', 'North', 'Online', 1, 1000, 0, 'Completed', 1000, 1, NULL);"""
        )
        conn.commit()

    res = analytics.get_top_product_by_revenue(db_file)
    assert res["result"]["top_product"] == "Alpha"  # Alphabetical tie-break


def test_narrative_number_verification():
    """Verify narrative number verification catches hallucinations."""
    facts = {"total_revenue": 1439200.0, "units": 48}

    # True narrative: numbers 1,439,200 and 48 exist in facts
    valid_narrative = "Total revenue reached 1,439,200 with 48 units sold."
    assert analytics.verify_narrative_numbers(valid_narrative, facts) is True

    # Hallucinated narrative: 999,999 does not exist in facts
    invalid_narrative = "Total revenue reached 999,999 across all stores."
    assert analytics.verify_narrative_numbers(invalid_narrative, facts) is False
