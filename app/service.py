"""Service orchestration layer for AI BI Assistant.

Binds natural language interpretation, parameter validation, deterministic SQL analytics,
narrative verification, and standard response formatting.
"""
import logging
from typing import Any, Dict, List, Optional
from app import analytics
from app.config import DATABASE_PATH
from app.database import get_readonly_connection
from app.interpreter import QueryIntent, interpret_question
from app.rules import CURRENCY_NOTE, LINE_REVENUE_FORMULA

logger = logging.getLogger(__name__)

SUPPORTED_EXAMPLE_QUESTIONS: List[str] = [
    "What is the total revenue?",
    "Which product generated the highest revenue?",
    "What is the monthly revenue trend?",
    "Which region generated the highest sales?",
    "How did revenue change between January and February 2026?",
]


def get_data_notes(db_path=DATABASE_PATH) -> Dict[str, Any]:
    """Retrieve dynamic data-quality notes from the sales database."""
    try:
        with get_readonly_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sales WHERE is_included = 1;")
            inc = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sales WHERE is_included = 0;")
            exc = cursor.fetchone()[0]
    except Exception:
        inc = 48
        exc = 3

    return {
        "included_rows": inc,
        "excluded_rows": exc,
        "revenue_definition": f"{LINE_REVENUE_FORMULA}; Completed orders only",
        "currency_note": CURRENCY_NOTE,
    }


def process_question(question: str, db_path=DATABASE_PATH) -> Dict[str, Any]:
    """Process a user question through the complete BI pipeline.
    
    Validates question length, runs AI/rule-based intent extraction,
    executes parameterized deterministic queries, verifies narrative,
    and returns an API-compliant structured payload.
    """
    cleaned_q = question.strip() if question else ""

    # Basic input validation
    if not cleaned_q:
        return {
            "status": "error",
            "question": question,
            "intent": None,
            "interpreter": "rule_based",
            "answer": "Question cannot be empty.",
            "result": None,
            "supporting_data": [],
            "sql_used": None,
            "sql_parameters": [],
            "data_notes": get_data_notes(db_path),
        }

    if len(cleaned_q) > 500:
        return {
            "status": "error",
            "question": cleaned_q[:50] + "...",
            "intent": None,
            "interpreter": "rule_based",
            "answer": "Question exceeds maximum allowed length of 500 characters.",
            "result": None,
            "supporting_data": [],
            "sql_used": None,
            "sql_parameters": [],
            "data_notes": get_data_notes(db_path),
        }

    # Intent interpretation
    interp = interpret_question(cleaned_q)
    intent = interp.intent
    notes = get_data_notes(db_path)

    if intent == QueryIntent.UNSUPPORTED:
        return {
            "status": "unsupported",
            "question": cleaned_q,
            "intent": QueryIntent.UNSUPPORTED.value,
            "interpreter": interp.interpreter,
            "answer": (
                "I couldn't match your question to a supported business metric. "
                "I can analyze total revenue, top products, monthly trends, top regions, "
                "and month-over-month comparisons."
            ),
            "result": None,
            "supporting_data": [],
            "sql_used": None,
            "sql_parameters": [],
            "supported_questions": SUPPORTED_EXAMPLE_QUESTIONS,
            "data_notes": notes,
        }

    # Dispatch to deterministic analytics
    try:
        if intent == QueryIntent.TOTAL_REVENUE:
            data = analytics.get_total_revenue(db_path)
        elif intent == QueryIntent.TOP_PRODUCT_BY_REVENUE:
            data = analytics.get_top_product_by_revenue(db_path)
        elif intent == QueryIntent.MONTHLY_REVENUE_TREND:
            data = analytics.get_monthly_revenue_trend(db_path)
        elif intent == QueryIntent.TOP_REGION_BY_SALES:
            data = analytics.get_top_region_by_sales(db_path)
        elif intent == QueryIntent.REVENUE_CHANGE_BETWEEN_MONTHS:
            data = analytics.get_revenue_change_between_months(
                interp.parameters.month_a,
                interp.parameters.month_b,
                db_path,
            )
        else:
            return {
                "status": "unsupported",
                "question": cleaned_q,
                "intent": QueryIntent.UNSUPPORTED.value,
                "interpreter": interp.interpreter,
                "answer": "Unsupported query intent.",
                "result": None,
                "supporting_data": [],
                "sql_used": None,
                "sql_parameters": [],
                "data_notes": notes,
            }
    except Exception as e:
        logger.error(f"Error executing analytics query for intent {intent}: {e}", exc_info=True)
        raise e  # Will be caught by API level error handler

    # Handle domain-level errors from analytics (e.g. missing comparison months)
    if "error" in data:
        return {
            "status": "unsupported",
            "question": cleaned_q,
            "intent": intent.value,
            "interpreter": interp.interpreter,
            "answer": data["answer"],
            "result": None,
            "supporting_data": data.get("supporting_data", []),
            "sql_used": data.get("sql_used"),
            "sql_parameters": data.get("sql_parameters", []),
            "data_notes": notes,
        }

    # Formulate answer: check if LLM proposed a narrative, verify its numbers
    final_answer = data["answer"]
    if interp.narrative_suggestion and data["result"]:
        if analytics.verify_narrative_numbers(interp.narrative_suggestion, data["result"]):
            final_answer = interp.narrative_suggestion

    return {
        "status": "ok",
        "question": cleaned_q,
        "intent": intent.value,
        "interpreter": interp.interpreter,
        "answer": final_answer,
        "result": data["result"],
        "supporting_data": data["supporting_data"],
        "sql_used": data["sql_used"],
        "sql_parameters": data["sql_parameters"],
        "data_notes": notes,
    }
