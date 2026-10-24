"""FastAPI backend application for the Mini AI Business Intelligence Assistant.

Exposes REST endpoints for querying sales analytics, checking system health,
inspecting data quality audit trails, and listing supported questions.
"""
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import CSV_DATA_PATH, DATABASE_PATH
from app.database import get_readonly_connection
from app.loader import load_csv_data
from app.service import SUPPORTED_EXAMPLE_QUESTIONS, process_question

# Configure server logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to ensure DB is initialized on startup."""
    logger.info("Initializing application and ensuring database is populated...")
    try:
        # Check if DB exists and has records; if not, load from CSV
        if not DATABASE_PATH.exists():
            logger.info(f"Database not found at {DATABASE_PATH}. Loading CSV...")
            load_csv_data(CSV_DATA_PATH, DATABASE_PATH)
        else:
            with get_readonly_connection(DATABASE_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM sales;")
                count = cursor.fetchone()[0]
                if count == 0:
                    logger.info("Sales table empty. Loading CSV...")
                    load_csv_data(CSV_DATA_PATH, DATABASE_PATH)
                else:
                    logger.info(f"Database ready with {count} rows.")
    except Exception as e:
        logger.warning(f"Startup check failed: {e}. Attempting full reload...")
        try:
            load_csv_data(CSV_DATA_PATH, DATABASE_PATH)
        except Exception as err:
            logger.error(f"Failed to initialize database: {err}", exc_info=True)

    yield
    logger.info("Application shutting down.")


app = FastAPI(
    title="Mini AI Business Intelligence Assistant",
    description="Natural language question answering over sales data backed by deterministic SQL.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for local Streamlit UI integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(
        ...,
        description="The natural language question to ask the BI assistant.",
        min_length=1,
        max_length=500,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler: logs internals server-side and returns a safe HTTP 500 response."""
    logger.error(f"Unhandled exception processing {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": "An internal server error occurred while processing your request.",
        },
    )


@app.post("/ask", summary="Ask a natural language business question")
def ask_question(req: AskRequest) -> Dict[str, Any]:
    """Accept natural language query, interpret intent, execute deterministic SQL, and return facts."""
    try:
        return process_question(req.question, db_path=DATABASE_PATH)
    except Exception as e:
        logger.error(f"Error processing question '{req.question}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while evaluating the query.",
        )


@app.get("/health", summary="Service health and database status check")
def health_check() -> Dict[str, Any]:
    """Check database reachability and return row counts."""
    try:
        with get_readonly_connection(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sales WHERE is_included = 1;")
            inc = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sales WHERE is_included = 0;")
            exc = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sales;")
            total = cursor.fetchone()[0]

        return {
            "status": "ok",
            "database": "connected",
            "total_rows": total,
            "included_rows": inc,
            "excluded_rows": exc,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "error",
            "database": "unreachable",
            "error": str(e),
        }


@app.get("/supported-questions", summary="List supported question templates and intents")
def get_supported_questions() -> Dict[str, Any]:
    """List sample questions supported by the deterministic analytics engine."""
    return {
        "status": "ok",
        "supported_questions": SUPPORTED_EXAMPLE_QUESTIONS,
        "supported_intents": [
            "total_revenue",
            "top_product_by_revenue",
            "monthly_revenue_trend",
            "top_region_by_sales",
            "revenue_change_between_months",
        ],
    }


@app.get("/data-quality", summary="Inspect data quality exclusions and audit trail")
def get_data_quality() -> Dict[str, Any]:
    """Return audit log of excluded records along with rationale."""
    try:
        with get_readonly_connection(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT transaction_id, order_date, product, quantity, unit_price, status, exclusion_reason "
                "FROM sales WHERE is_included = 0;"
            )
            rows = [dict(r) for r in cursor.fetchall()]

        return {
            "status": "ok",
            "excluded_count": len(rows),
            "excluded_records": rows,
            "rules": {
                "included_criteria": "Status == 'Completed', Quantity > 0, Unit_price is present & >= 0, Discount <= Gross, Valid date",
                "exclusion_policy": "Excluded rows are preserved in SQLite with is_included=0 and exclusion_reason. Never deleted or altered.",
            },
        }
    except Exception as e:
        logger.error(f"Failed to fetch data quality report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve data quality audit log.",
        )
