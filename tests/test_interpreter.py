"""Tests for intent interpretation, synonym parsing, Pydantic validation, and LLM fallback."""
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError

from app.interpreter import (
    IntentParameters,
    InterpreterResult,
    QueryIntent,
    extract_months_from_text,
    interpret_question,
    parse_month_token,
    rule_based_interpret,
)


@pytest.mark.parametrize(
    "question,expected_intent",
    [
        ("What is the total revenue?", QueryIntent.TOTAL_REVENUE),
        ("Total sales across all stores", QueryIntent.TOTAL_REVENUE),
        ("How much money did we make?", QueryIntent.TOTAL_REVENUE),
        ("overall revenue", QueryIntent.TOTAL_REVENUE),
        ("Which product generated the highest revenue?", QueryIntent.TOP_PRODUCT_BY_REVENUE),
        ("What is our top product?", QueryIntent.TOP_PRODUCT_BY_REVENUE),
        ("best selling product by revenue", QueryIntent.TOP_PRODUCT_BY_REVENUE),
        ("What is the monthly revenue trend?", QueryIntent.MONTHLY_REVENUE_TREND),
        ("Show me monthly trend of sales", QueryIntent.MONTHLY_REVENUE_TREND),
        ("month by month revenue", QueryIntent.MONTHLY_REVENUE_TREND),
        ("Which region generated the highest sales?", QueryIntent.TOP_REGION_BY_SALES),
        ("top region by sales", QueryIntent.TOP_REGION_BY_SALES),
        ("best performing sales region", QueryIntent.TOP_REGION_BY_SALES),
        ("How did revenue change between January and February 2026?", QueryIntent.REVENUE_CHANGE_BETWEEN_MONTHS),
        ("compare revenue between Jan and March", QueryIntent.REVENUE_CHANGE_BETVENUE_CHANGE_BETWEEN_MONTHS if hasattr(QueryIntent, "REVENUE_CHANGE_BETVENUE_CHANGE_BETWEEN_MONTHS") else QueryIntent.REVENUE_CHANGE_BETWEEN_MONTHS),
        ("revenue difference between 2026-01 and 2026-04", QueryIntent.REVENUE_CHANGE_BETWEEN_MONTHS),
        ("growth from February to May", QueryIntent.REVENUE_CHANGE_BETWEEN_MONTHS),
    ],
)
def test_rule_based_paraphrase_coverage(question: str, expected_intent: QueryIntent):
    """Assert rule-based interpreter correctly identifies intents from varied phrasing."""
    res = rule_based_interpret(question)
    assert res.intent == expected_intent


def test_rule_based_unsupported_question():
    """Assert non-BI / unsupported questions return UNSUPPORTED intent."""
    res = rule_based_interpret("Who is the CEO of the company?")
    assert res.intent == QueryIntent.UNSUPPORTED
    assert res.confidence == 0.0


def test_month_extraction_formats():
    """Assert extraction of month names, abbreviations, and ISO formats."""
    # Names with year
    m1 = extract_months_from_text("Compare January 2026 and March 2026")
    assert m1 == ["2026-01", "2026-03"]

    # Abbreviations
    m2 = extract_months_from_text("Difference between Feb and Apr")
    assert m2 == ["2026-02", "2026-04"]

    # ISO format
    m3 = extract_months_from_text("Change between 2026-01 and 2026-05")
    assert m3 == ["2026-01", "2026-05"]


def test_pydantic_schema_validation_rejects_malformed_month():
    """Assert Pydantic rejects non YYYY-MM month parameter formats."""
    with pytest.raises(ValidationError):
        IntentParameters(month_a="2026-99")  # Invalid month 99

    with pytest.raises(ValidationError):
        IntentParameters(month_a="SELECT * FROM users")  # Hostile SQL in parameter!


def test_pydantic_schema_validation_rejects_unknown_intent():
    """Assert Pydantic rejects intent values outside the enum."""
    with pytest.raises(ValidationError):
        InterpreterResult(intent="execute_arbitrary_code")


def test_llm_failure_triggers_automatic_rule_based_fallback():
    """Assert when LLM fails or times out, the service falls back gracefully to rule-based."""
    with patch("app.interpreter.LLM_PROVIDER", "gemini"), \
         patch("app.interpreter.GEMINI_API_KEY", "fake_key_12345"), \
         patch("app.interpreter.llm_interpret", return_value=None):

        res = interpret_question("What is the total revenue?")
        # LLM failed, so interpreter should be rule_based and intent correct
        assert res.interpreter == "rule_based"
        assert res.intent == QueryIntent.TOTAL_REVENUE
