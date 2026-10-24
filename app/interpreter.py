"""Query interpreter module with Pydantic validation and offline fallback.

Translates natural language questions into structured, validated intents and parameters.
The LLM is strictly constrained: it only extracts intent and parameters as JSON.
It never writes SQL, never queries the database, and never calculates numbers.
"""
import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator

from app.config import GEMINI_API_KEY, GEMINI_MODEL, LLM_PROVIDER

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    TOTAL_REVENUE = "total_revenue"
    TOP_PRODUCT_BY_REVENUE = "top_product_by_revenue"
    MONTHLY_REVENUE_TREND = "monthly_revenue_trend"
    TOP_REGION_BY_SALES = "top_region_by_sales"
    REVENUE_CHANGE_BETWEEN_MONTHS = "revenue_change_between_months"
    UNSUPPORTED = "unsupported"


class IntentParameters(BaseModel):
    month_a: Optional[str] = None
    month_b: Optional[str] = None

    @field_validator("month_a", "month_b")
    @classmethod
    def validate_month_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        # Strictly ensure YYYY-MM format
        if not re.match(r"^202[0-9]-(0[1-9]|1[0-2])$", v):
            raise ValueError(f"Month parameter must be in YYYY-MM format, got: '{v}'")
        return v


class InterpreterResult(BaseModel):
    intent: QueryIntent
    parameters: IntentParameters = Field(default_factory=IntentParameters)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    interpreter: str = "rule_based"  # 'llm' or 'rule_based'
    narrative_suggestion: Optional[str] = None


# Month mapping utilities for normalization (Jan -> 2026-01)
MONTH_NAMES = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}


def parse_month_token(token: str, default_year: str = "2026") -> Optional[str]:
    """Parse various natural representations of months into YYYY-MM format."""
    clean = token.strip().lower()

    # Match YYYY-MM directly
    m_iso = re.match(r"^(20\d\d)-(0[1-9]|1[0-2])$", clean)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}"

    # Match MM/YYYY or MM-YYYY
    m_slash = re.match(r"^(0?[1-9]|1[0-2])[/-](20\d\d)$", clean)
    if m_slash:
        m_num = int(m_slash.group(1))
        return f"{m_slash.group(2)}-{m_num:02d}"

    # Match month name with optional year (e.g., 'January 2026', 'jan 2026', 'January')
    words = clean.split()
    for word in words:
        if word in MONTH_NAMES:
            month_num = MONTH_NAMES[word]
            # Look for 4-digit year in words
            year = default_year
            for w in words:
                if re.match(r"^20\d\d$", w):
                    year = w
                    break
            return f"{year}-{month_num}"

    return None


def extract_months_from_text(text: str) -> List[str]:
    """Extract up to two months mentioned in the query text."""
    lower = text.lower()
    months_found: List[Tuple[int, str]] = []  # (index, YYYY-MM)

    # 1. Look for ISO YYYY-MM
    for match in re.finditer(r"\b(20\d\d)-(0[1-9]|1[0-2])\b", lower):
        months_found.append((match.start(), match.group(0)))

    # 2. Look for month names
    for m_name, m_num in MONTH_NAMES.items():
        pattern = rf"\b{m_name}\b(?:\s+(20\d\d))?"
        for match in re.finditer(pattern, lower):
            idx = match.start()
            year = match.group(1) if match.group(1) else "2026"
            iso = f"{year}-{m_num}"
            # Avoid duplicate overlapping match
            if not any(abs(idx - existing_idx) < 5 for existing_idx, _ in months_found):
                months_found.append((idx, iso))

    # Sort by appearance order in string
    months_found.sort(key=lambda x: x[0])
    # Deduplicate while preserving order
    unique_months = []
    for _, iso in months_found:
        if iso not in unique_months:
            unique_months.append(iso)

    return unique_months


def rule_based_interpret(question: str) -> InterpreterResult:
    """Deterministically classify intent using pattern matching and synonyms."""
    q = question.strip().lower()

    # 1. Total revenue patterns
    if (
        re.search(r"\b(total|overall|gross|entire)\s+(revenue|sales|income|turnover)\b", q)
        or re.search(r"\bhow much (money|revenue|sales)\b", q)
        or q in {"what is the total revenue?", "what is the total revenue", "total revenue"}
    ):
        return InterpreterResult(
            intent=QueryIntent.TOTAL_REVENUE,
            parameters=IntentParameters(),
            confidence=1.0,
            interpreter="rule_based",
        )

    # 2. Top product patterns
    if (
        re.search(r"\b(which|what|top|best|highest|leading)\s+(?:(?:selling|performing)\s+)?(?:(?:revenue|sales)\s+)?product\b", q)
        or re.search(r"\bproduct\s+(?:generated|made|produced|with)\s+(?:the\s+)?(?:highest|most|maximum|top)\s+(?:revenue|sales)\b", q)
        or re.search(r"\bhighest\s+revenue\s+product\b", q)
        or re.search(r"\bbest\s+selling\s+product\b", q)
        or q in {"which product generated the highest revenue?", "which product generated the highest revenue"}
    ):
        return InterpreterResult(
            intent=QueryIntent.TOP_PRODUCT_BY_REVENUE,
            parameters=IntentParameters(),
            confidence=1.0,
            interpreter="rule_based",
        )

    # 3. Revenue change between months
    if (
        re.search(r"\b(change|difference|diff|growth|comparison|compare|delta|versus|vs)\b", q)
        and ("month" in q or "between" in q or "from" in q or any(m in q for m in MONTH_NAMES))
    ) or (
        re.search(r"\bhow did revenue change\b", q)
    ):
        months = extract_months_from_text(question)
        month_a = months[0] if len(months) >= 1 else None
        month_b = months[1] if len(months) >= 2 else None

        return InterpreterResult(
            intent=QueryIntent.REVENUE_CHANGE_BETWEEN_MONTHS,
            parameters=IntentParameters(month_a=month_a, month_b=month_b),
            confidence=0.95 if (month_a and month_b) else 0.7,
            interpreter="rule_based",
        )

    # 4. Monthly revenue trend patterns
    if (
        re.search(r"\b(monthly|month[- ]by[- ]month)\s+(revenue|sales|trend|growth|breakdown)\b", q)
        or re.search(r"\b(revenue|sales)\s+(trend|trajectory|by month|per month|over time)\b", q)
        or q in {"what is the monthly revenue trend?", "what is the monthly revenue trend", "monthly trend"}
    ):
        return InterpreterResult(
            intent=QueryIntent.MONTHLY_REVENUE_TREND,
            parameters=IntentParameters(),
            confidence=1.0,
            interpreter="rule_based",
        )

    # 5. Top region patterns
    if (
        re.search(r"\b(which|what|top|best|highest|leading)\s+(?:(?:performing|selling)\s+)?(?:(?:sales|revenue)\s+)?region\b", q)
        or re.search(r"\bregion\s+(?:generated|made|produced|with)\s+(?:the\s+)?(?:highest|most|maximum|top)\s+(?:revenue|sales)\b", q)
        or re.search(r"\bhighest\s+(?:sales|revenue)\s+region\b", q)
        or re.search(r"\b(top|best)\s+region\b", q)
        or q in {"which region generated the highest sales?", "which region generated the highest sales"}
    ):
        return InterpreterResult(
            intent=QueryIntent.TOP_REGION_BY_SALES,
            parameters=IntentParameters(),
            confidence=1.0,
            interpreter="rule_based",
        )

    # Unsupported / unclassified question
    return InterpreterResult(
        intent=QueryIntent.UNSUPPORTED,
        parameters=IntentParameters(),
        confidence=0.0,
        interpreter="rule_based",
    )


def llm_interpret(question: str) -> Optional[InterpreterResult]:
    """Attempt LLM interpretation using Google Gemini if configured.
    
    Returns None if LLM is unavailable, times out, or fails schema validation,
    triggering the automatic fallback.
    """
    if LLM_PROVIDER != "gemini" or not GEMINI_API_KEY:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        system_instruction = (
            "You are a strict natural language query classifier for a Sales BI Assistant. "
            "Your ONLY responsibility is to categorize the user question into one of the allowed intents, "
            "and extract month parameters if present. "
            "NEVER generate SQL. NEVER execute database operations. NEVER invent or compute numbers. "
            "Output must be STRICT valid JSON matching this schema:\n"
            "{\n"
            '  "intent": "total_revenue" | "top_product_by_revenue" | "monthly_revenue_trend" | "top_region_by_sales" | "revenue_change_between_months" | "unsupported",\n'
            '  "parameters": {"month_a": "YYYY-MM" or null, "month_b": "YYYY-MM" or null},\n'
            '  "confidence": 0.0 to 1.0\n'
            "}"
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )

        raw_json = response.text.strip()
        data = json.loads(raw_json)

        # Validate with Pydantic
        intent_enum = QueryIntent(data.get("intent", "unsupported"))
        raw_params = data.get("parameters", {})
        params = IntentParameters(
            month_a=raw_params.get("month_a"),
            month_b=raw_params.get("month_b"),
        )
        conf = float(data.get("confidence", 0.9))

        return InterpreterResult(
            intent=intent_enum,
            parameters=params,
            confidence=conf,
            interpreter="llm",
        )
    except Exception as e:
        logger.warning(f"LLM interpretation failed or timed out: {e}. Falling back to rule-based.")
        return None


def interpret_question(question: str) -> InterpreterResult:
    """Primary entry point: attempts LLM interpretation, falls back to rule-based parser."""
    # Attempt LLM if configured
    if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
        result = llm_interpret(question)
        if result is not None:
            return result

    # Standard / Offline path
    return rule_based_interpret(question)
