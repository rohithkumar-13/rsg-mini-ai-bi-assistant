"""Tests for FastAPI endpoints using TestClient."""
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.config import DATABASE_PATH
from app.database import get_readonly_connection
from app.main import app


@pytest.fixture
def client(loaded_temp_db: Path) -> TestClient:
    """Provide a TestClient connected to the loaded test database."""
    with patch("app.main.DATABASE_PATH", loaded_temp_db), \
         patch("app.service.DATABASE_PATH", loaded_temp_db), \
         patch("app.analytics.DATABASE_PATH", loaded_temp_db):
        yield TestClient(app)


def test_api_ask_valid_question(client: TestClient):
    """Assert POST /ask returns the full structured response schema."""
    resp = client.post("/ask", json={"question": "What is the total revenue?"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert data["intent"] == "total_revenue"
    assert data["interpreter"] in ("llm", "rule_based")
    assert "1,439,200" in data["answer"]
    assert data["result"]["total_revenue"] == 1439200.0
    assert len(data["supporting_data"]) > 0
    assert "SELECT" in data["sql_used"]
    assert isinstance(data["sql_parameters"], list)
    assert data["data_notes"]["included_rows"] == 48
    assert data["data_notes"]["excluded_rows"] == 3


def test_api_ask_unsupported_question(client: TestClient):
    """Assert unsupported question returns 200 with status='unsupported' and guided options."""
    resp = client.post("/ask", json={"question": "Who is the CEO of Google?"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "unsupported"
    assert data["intent"] == "unsupported"
    assert "supported_questions" in data
    assert len(data["supported_questions"]) >= 5


def test_api_ask_sql_injection_attempt_is_harmless(client: TestClient, loaded_temp_db: Path):
    """Assert hostile SQL injection string is harmless and table remains intact."""
    injection_payload = "'; DROP TABLE sales; SELECT * FROM sales WHERE '1'='1"
    resp = client.post("/ask", json={"question": injection_payload})
    assert resp.status_code == 200

    # Verify database table is completely intact with all rows
    with get_readonly_connection(loaded_temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sales;")
        count = cursor.fetchone()[0]
        assert count == 51


def test_api_ask_empty_question(client: TestClient):
    """Assert empty question returns error status."""
    resp = client.post("/ask", json={"question": "   "})
    # Pydantic or service handles empty string
    assert resp.status_code in (200, 422)
    if resp.status_code == 200:
        data = resp.json()
        assert data["status"] in ("error", "unsupported")


def test_api_ask_overlong_question(client: TestClient):
    """Assert questions exceeding 500 characters are rejected."""
    long_question = "What is the revenue? " * 50  # Over 500 chars
    resp = client.post("/ask", json={"question": long_question})
    assert resp.status_code in (200, 422)
    if resp.status_code == 200:
        assert resp.json()["status"] == "error"


def test_api_health_endpoint(client: TestClient):
    """Assert GET /health returns DB connection status and row metrics."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert data["total_rows"] == 51
    assert data["included_rows"] == 48
    assert data["excluded_rows"] == 3


def test_api_supported_questions_endpoint(client: TestClient):
    """Assert GET /supported-questions lists all 5 query templates."""
    resp = client.get("/supported-questions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["supported_questions"]) == 5
    assert len(data["supported_intents"]) == 5


def test_api_data_quality_endpoint(client: TestClient):
    """Assert GET /data-quality returns audit logs for the 3 excluded records."""
    resp = client.get("/data-quality")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["excluded_count"] == 3
    tids = [r["transaction_id"] for r in data["excluded_records"]]
    assert "TXN0033" in tids
    assert "TXN0034" in tids
    assert "TXN0051" in tids


def test_api_simulated_db_error_returns_safe_500(client: TestClient):
    """Assert internal DB errors return safe 500 without leaking stack traces or SQL details."""
    with patch("app.service.analytics.get_total_revenue", side_effect=RuntimeError("Secret SQLite connection password")):
        resp = client.post("/ask", json={"question": "What is the total revenue?"})
        assert resp.status_code == 500
        data = resp.json()
        # Message must be safe and generic
        assert "Secret" not in data.get("detail", "")
        assert "SQLite" not in data.get("detail", "")
