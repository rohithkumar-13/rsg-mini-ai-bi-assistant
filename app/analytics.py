"""Deterministic analytics query module.

Executes strictly parameterized, read-only SQL queries corresponding to the
supported business intelligence questions. Enforces defense-in-depth security via
sql_guard and ensures deterministic tie-breaking.
"""
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path
from app.config import DATABASE_PATH
from app.database import get_readonly_connection
from app.sql_guard import validate_select_only

# Deterministic SQL templates (using ? parameter placeholders only)
SQL_TOTAL_REVENUE = """
SELECT 
    COALESCE(SUM(line_revenue), 0) AS total_revenue,
    COUNT(*) AS transaction_count,
    COALESCE(SUM(quantity), 0) AS total_units
FROM sales 
WHERE is_included = 1
"""

SQL_TOP_PRODUCT = """
SELECT 
    product,
    COALESCE(SUM(line_revenue), 0) AS total_revenue,
    COALESCE(SUM(quantity), 0) AS total_quantity,
    COUNT(*) AS transaction_count
FROM sales 
WHERE is_included = 1 
GROUP BY product 
ORDER BY total_revenue DESC, product ASC 
LIMIT 1
"""

SQL_ALL_PRODUCTS_SUPPORTING = """
SELECT 
    product,
    COALESCE(SUM(line_revenue), 0) AS total_revenue,
    COALESCE(SUM(quantity), 0) AS total_quantity,
    COUNT(*) AS transaction_count
FROM sales 
WHERE is_included = 1 
GROUP BY product 
ORDER BY total_revenue DESC, product ASC
"""

SQL_MONTHLY_TREND = """
SELECT 
    order_month,
    COALESCE(SUM(line_revenue), 0) AS monthly_revenue,
    COALESCE(SUM(quantity), 0) AS total_quantity,
    COUNT(*) AS transaction_count
FROM sales 
WHERE is_included = 1 
GROUP BY order_month 
ORDER BY order_month ASC
"""

SQL_TOP_REGION = """
SELECT 
    region,
    COALESCE(SUM(line_revenue), 0) AS total_revenue,
    COALESCE(SUM(quantity), 0) AS total_quantity,
    COUNT(*) AS transaction_count
FROM sales 
WHERE is_included = 1 
GROUP BY region 
ORDER BY total_revenue DESC, region ASC 
LIMIT 1
"""

SQL_ALL_REGIONS_SUPPORTING = """
SELECT 
    region,
    COALESCE(SUM(line_revenue), 0) AS total_revenue,
    COALESCE(SUM(quantity), 0) AS total_quantity,
    COUNT(*) AS transaction_count
FROM sales 
WHERE is_included = 1 
GROUP BY region 
ORDER BY total_revenue DESC, region ASC
"""

SQL_MONTH_SPECIFIC = """
SELECT 
    order_month,
    COALESCE(SUM(line_revenue), 0) AS monthly_revenue,
    COALESCE(SUM(quantity), 0) AS total_quantity,
    COUNT(*) AS transaction_count
FROM sales 
WHERE is_included = 1 AND order_month = ?
GROUP BY order_month
"""


def _execute_safe_query(
    sql: str,
    params: Tuple[Any, ...] = (),
    db_path: Union[str, Path] = DATABASE_PATH,
) -> List[Dict[str, Any]]:
    """Validate query with sql_guard and execute on read-only SQLite connection."""
    validate_select_only(sql)
    with get_readonly_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_total_revenue(db_path: Union[str, Path] = DATABASE_PATH) -> Dict[str, Any]:
    """Calculate aggregate revenue across all included transactions."""
    rows = _execute_safe_query(SQL_TOTAL_REVENUE, (), db_path)
    res = rows[0] if rows else {"total_revenue": 0.0, "transaction_count": 0, "total_units": 0}
    total_rev = float(res["total_revenue"])
    tx_count = int(res["transaction_count"])
    units = int(res["total_units"])

    template_answer = (
        f"Total revenue is {total_rev:,.0f} across {tx_count} completed transactions ({units:,} units sold)."
    )

    return {
        "answer": template_answer,
        "result": {
            "total_revenue": total_rev,
            "transaction_count": tx_count,
            "total_units": units,
        },
        "supporting_data": rows,
        "sql_used": SQL_TOTAL_REVENUE.strip(),
        "sql_parameters": [],
    }


def get_top_product_by_revenue(db_path: Union[str, Path] = DATABASE_PATH) -> Dict[str, Any]:
    """Identify the product generating the highest revenue, with deterministic tie-break."""
    top_rows = _execute_safe_query(SQL_TOP_PRODUCT, (), db_path)
    all_rows = _execute_safe_query(SQL_ALL_PRODUCTS_SUPPORTING, (), db_path)

    if not top_rows:
        return {
            "answer": "No completed transactions found.",
            "result": {"top_product": None, "revenue": 0.0, "quantity": 0},
            "supporting_data": [],
            "sql_used": SQL_TOP_PRODUCT.strip(),
            "sql_parameters": [],
        }

    top = top_rows[0]
    prod = top["product"]
    rev = float(top["total_revenue"])
    qty = int(top["total_quantity"])

    template_answer = (
        f"The product with the highest revenue is {prod} with {rev:,.0f} across {qty:,} units sold."
    )

    return {
        "answer": template_answer,
        "result": {
            "top_product": prod,
            "revenue": rev,
            "quantity": qty,
            "transaction_count": int(top["transaction_count"]),
        },
        "supporting_data": all_rows,
        "sql_used": SQL_TOP_PRODUCT.strip(),
        "sql_parameters": [],
    }


def get_monthly_revenue_trend(db_path: Union[str, Path] = DATABASE_PATH) -> Dict[str, Any]:
    """Retrieve month-by-month revenue trajectory."""
    rows = _execute_safe_query(SQL_MONTHLY_TREND, (), db_path)
    if not rows:
        return {
            "answer": "No completed transactions found for monthly trend.",
            "result": {"months": []},
            "supporting_data": [],
            "sql_used": SQL_MONTHLY_TREND.strip(),
            "sql_parameters": [],
        }

    peak_month = max(rows, key=lambda r: r["monthly_revenue"])
    first_month = rows[0]["order_month"]
    last_month = rows[-1]["order_month"]

    template_answer = (
        f"Monthly revenue covers {len(rows)} months from {first_month} to {last_month}, "
        f"peaking in {peak_month['order_month']} at {float(peak_month['monthly_revenue']):,.0f}."
    )

    return {
        "answer": template_answer,
        "result": {
            "months_count": len(rows),
            "start_month": first_month,
            "end_month": last_month,
            "peak_month": peak_month["order_month"],
            "peak_revenue": float(peak_month["monthly_revenue"]),
        },
        "supporting_data": rows,
        "sql_used": SQL_MONTHLY_TREND.strip(),
        "sql_parameters": [],
    }


def get_top_region_by_sales(db_path: Union[str, Path] = DATABASE_PATH) -> Dict[str, Any]:
    """Identify the region generating the highest revenue, with deterministic tie-break."""
    top_rows = _execute_safe_query(SQL_TOP_REGION, (), db_path)
    all_rows = _execute_safe_query(SQL_ALL_REGIONS_SUPPORTING, (), db_path)

    if not top_rows:
        return {
            "answer": "No completed transactions found.",
            "result": {"top_region": None, "revenue": 0.0},
            "supporting_data": [],
            "sql_used": SQL_TOP_REGION.strip(),
            "sql_parameters": [],
        }

    top = top_rows[0]
    reg = top["region"]
    rev = float(top["total_revenue"])
    tx_count = int(top["transaction_count"])

    template_answer = (
        f"The region with the highest sales is {reg} with {rev:,.0f} across {tx_count} transactions."
    )

    return {
        "answer": template_answer,
        "result": {
            "top_region": reg,
            "revenue": rev,
            "transaction_count": tx_count,
            "quantity": int(top["total_quantity"]),
        },
        "supporting_data": all_rows,
        "sql_used": SQL_TOP_REGION.strip(),
        "sql_parameters": [],
    }


def get_revenue_change_between_months(
    month_a: Optional[str],
    month_b: Optional[str],
    db_path: Union[str, Path] = DATABASE_PATH,
) -> Dict[str, Any]:
    """Calculate revenue comparison between two specified months (YYYY-MM).
    
    Handles missing months, non-existent data, zero base revenue, and same-month queries.
    """
    if not month_a or not month_b:
        return {
            "error": "Both month_a and month_b (in YYYY-MM format) must be provided for comparison.",
            "answer": "Please provide both months to compare (e.g. 'Compare revenue between January and February 2026').",
            "result": None,
            "supporting_data": [],
            "sql_used": None,
            "sql_parameters": [],
        }

    # Fetch data for month_a
    res_a = _execute_safe_query(SQL_MONTH_SPECIFIC, (month_a,), db_path)
    # Fetch data for month_b
    res_b = _execute_safe_query(SQL_MONTH_SPECIFIC, (month_b,), db_path)

    if not res_a and not res_b:
        return {
            "error": f"No data found for neither {month_a} nor {month_b}.",
            "answer": f"No sales data is available for {month_a} or {month_b}.",
            "result": None,
            "supporting_data": [],
            "sql_used": SQL_MONTH_SPECIFIC.strip(),
            "sql_parameters": [month_a, month_b],
        }
    if not res_a:
        return {
            "error": f"No sales data found for base month {month_a}.",
            "answer": f"No completed sales data is available for base month {month_a}.",
            "result": None,
            "supporting_data": res_b,
            "sql_used": SQL_MONTH_SPECIFIC.strip(),
            "sql_parameters": [month_a],
        }
    if not res_b:
        return {
            "error": f"No sales data found for comparison month {month_b}.",
            "answer": f"No completed sales data is available for target month {month_b}.",
            "result": None,
            "supporting_data": res_a,
            "sql_used": SQL_MONTH_SPECIFIC.strip(),
            "sql_parameters": [month_b],
        }

    rev_a = float(res_a[0]["monthly_revenue"])
    rev_b = float(res_b[0]["monthly_revenue"])
    diff = rev_b - rev_a

    if rev_a == 0:
        pct_change = None
        pct_str = "N/A (base month revenue was 0)"
    else:
        pct_change = round((diff / rev_a) * 100, 2)
        sign = "+" if pct_change > 0 else ""
        pct_str = f"{sign}{pct_change:.2f}%"

    direction = "increased" if diff > 0 else ("decreased" if diff < 0 else "remained unchanged")
    diff_sign = "+" if diff > 0 else ""

    template_answer = (
        f"Revenue changed from {rev_a:,.0f} in {month_a} to {rev_b:,.0f} in {month_b}, "
        f"which {direction} by {diff_sign}{diff:,.0f} ({pct_str})."
    )

    combined_supporting = res_a + res_b

    return {
        "answer": template_answer,
        "result": {
            "month_a": month_a,
            "revenue_a": rev_a,
            "month_b": month_b,
            "revenue_b": rev_b,
            "absolute_change": diff,
            "percentage_change": pct_change,
        },
        "supporting_data": combined_supporting,
        "sql_used": SQL_MONTH_SPECIFIC.strip(),
        "sql_parameters": [month_a, month_b],
    }


def verify_narrative_numbers(narrative: str, result_dict: Dict[str, Any]) -> bool:
    """Verify that every number mentioned in the generated narrative exists in result_dict.
    
    If any hallucinated or unverified number is found, returns False so the deterministic
    template answer is preserved instead.
    """
    if not narrative:
        return False

    # Extract all integer/float numbers from the narrative, ignoring punctuation and %
    # Matches patterns like 1,439,200 or 24,350 or 11.58 or 48
    raw_tokens = re.findall(r"[-+]?\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b", narrative)
    
    narrative_numbers = []
    for token in raw_tokens:
        clean = token.replace(",", "")
        try:
            val = float(clean)
            narrative_numbers.append(val)
        except ValueError:
            pass

    # Extract all numbers from result_dict values recursively
    known_numbers = set()

    def _collect_numbers(obj: Any) -> None:
        if isinstance(obj, (int, float)):
            known_numbers.add(round(float(obj), 2))
            known_numbers.add(round(float(obj), 0))
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect_numbers(v)
        elif isinstance(obj, list):
            for item in obj:
                _collect_numbers(item)

    _collect_numbers(result_dict)

    # Check each number in narrative against known numbers with small tolerance
    for num in narrative_numbers:
        rounded_2 = round(num, 2)
        rounded_0 = round(num, 0)
        # Check if matches any known number (or within 0.05 for rounding)
        matched = any(abs(num - k) < 0.1 for k in known_numbers)
        if not matched:
            return False

    return True
