"""Business rules and data validation definitions.

Single source of truth for:
- Line revenue formula
- Row inclusion criteria
- Exclusion reason codes
- Date parsing specifications
"""
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

# Business rule definitions
LINE_REVENUE_FORMULA: str = "Quantity * Unit_price - Discount_amount"
DATE_FORMAT_SOURCE: str = "%d-%m-%Y"
STATUS_COMPLETED: str = "completed"
STATUS_RETURNED: str = "returned"

# Exclusion reason constants
EXCLUSION_RETURNED: str = "returned"
EXCLUSION_ZERO_QUANTITY: str = "zero_quantity"
EXCLUSION_INVALID_QUANTITY: str = "invalid_quantity"
EXCLUSION_MISSING_PRICE: str = "missing_unit_price"
EXCLUSION_NEGATIVE_PRICE: str = "negative_unit_price"
EXCLUSION_INVALID_DISCOUNT: str = "invalid_discount"
EXCLUSION_INVALID_DATE: str = "invalid_date"
EXCLUSION_INVALID_STATUS: str = "invalid_status"
EXCLUSION_DUPLICATE_ID: str = "duplicate_transaction_id"

CURRENCY_NOTE: str = "Currency is unspecified in the source dataset. Amounts are presented with standard digit grouping."


def compute_line_revenue(quantity: int, unit_price: float, discount_amount: float) -> float:
    """Calculate line revenue as Quantity * Unit_price - Discount_amount.
    
    Discount_amount is applied as a total transaction discount, not per-unit.
    """
    return float(quantity * unit_price - discount_amount)


def validate_and_parse_row(row: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """Validate a raw CSV row against the strict business rules.
    
    Returns:
        (is_included, exclusion_reason, parsed_data_dict)
    """
    tid = str(row.get("Transaction_Id", "")).strip()
    raw_status = str(row.get("Status", "")).strip()
    raw_product = str(row.get("Product", "")).strip()
    raw_category = str(row.get("Category", "")).strip()
    raw_region = str(row.get("Region", "")).strip()
    raw_channel = str(row.get("Sales_channel", "")).strip()
    raw_date = str(row.get("Order_date", "")).strip()
    raw_qty = row.get("Quantity", "")
    raw_price = row.get("Unit_price", "")
    raw_discount = row.get("Discount_amount", "")

    parsed: Dict[str, Any] = {
        "transaction_id": tid,
        "order_date_raw": raw_date,
        "order_date": None,
        "order_month": None,
        "product": raw_product,
        "category": raw_category,
        "region": raw_region,
        "sales_channel": raw_channel,
        "quantity": None,
        "unit_price": None,
        "discount_amount": None,
        "status": raw_status,
        "line_revenue": None,
        "is_included": False,
        "exclusion_reason": None,
    }

    # 1. Date parsing
    try:
        dt = datetime.strptime(raw_date, DATE_FORMAT_SOURCE)
        parsed["order_date"] = dt.strftime("%Y-%m-%d")
        parsed["order_month"] = dt.strftime("%Y-%m")
    except Exception:
        parsed["exclusion_reason"] = EXCLUSION_INVALID_DATE
        return False, EXCLUSION_INVALID_DATE, parsed

    # 2. Status validation
    status_lower = raw_status.lower()
    if status_lower != STATUS_COMPLETED:
        reason = EXCLUSION_RETURNED if status_lower == STATUS_RETURNED else f"{EXCLUSION_INVALID_STATUS}_{status_lower}"
        parsed["exclusion_reason"] = reason
        # Parse numbers if possible for auditability
        try:
            parsed["quantity"] = int(raw_qty) if raw_qty != "" else None
            parsed["unit_price"] = float(raw_price) if raw_price != "" else None
            parsed["discount_amount"] = float(raw_discount) if raw_discount != "" else None
        except Exception:
            pass
        return False, reason, parsed

    # 3. Quantity validation
    try:
        if raw_qty is None or str(raw_qty).strip() == "":
            parsed["exclusion_reason"] = EXCLUSION_INVALID_QUANTITY
            return False, EXCLUSION_INVALID_QUANTITY, parsed
        qty = int(raw_qty)
        parsed["quantity"] = qty
        if qty == 0:
            parsed["exclusion_reason"] = EXCLUSION_ZERO_QUANTITY
            return False, EXCLUSION_ZERO_QUANTITY, parsed
        if qty < 0:
            parsed["exclusion_reason"] = EXCLUSION_INVALID_QUANTITY
            return False, EXCLUSION_INVALID_QUANTITY, parsed
    except ValueError:
        parsed["exclusion_reason"] = EXCLUSION_INVALID_QUANTITY
        return False, EXCLUSION_INVALID_QUANTITY, parsed

    # 4. Unit price validation (never impute missing price)
    try:
        if raw_price is None or str(raw_price).strip() == "":
            parsed["exclusion_reason"] = EXCLUSION_MISSING_PRICE
            return False, EXCLUSION_MISSING_PRICE, parsed
        price = float(raw_price)
        parsed["unit_price"] = price
        if price < 0:
            parsed["exclusion_reason"] = EXCLUSION_NEGATIVE_PRICE
            return False, EXCLUSION_NEGATIVE_PRICE, parsed
    except ValueError:
        parsed["exclusion_reason"] = EXCLUSION_MISSING_PRICE
        return False, EXCLUSION_MISSING_PRICE, parsed

    # 5. Discount validation
    try:
        if raw_discount is None or str(raw_discount).strip() == "":
            disc = 0.0
        else:
            disc = float(raw_discount)
        parsed["discount_amount"] = disc
        gross_total = qty * price
        if disc < 0 or disc > gross_total:
            parsed["exclusion_reason"] = EXCLUSION_INVALID_DISCOUNT
            return False, EXCLUSION_INVALID_DISCOUNT, parsed
    except ValueError:
        parsed["exclusion_reason"] = EXCLUSION_INVALID_DISCOUNT
        return False, EXCLUSION_INVALID_DISCOUNT, parsed

    # Row passed all rules
    parsed["line_revenue"] = compute_line_revenue(qty, price, disc)
    parsed["is_included"] = True
    parsed["exclusion_reason"] = None
    return True, None, parsed
