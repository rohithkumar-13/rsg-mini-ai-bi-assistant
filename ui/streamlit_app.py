"""Streamlit User Interface for Mini AI Business Intelligence Assistant.

Interacts with the FastAPI backend over HTTP to present natural language answers,
supporting data tables, dynamic trend charts, inspected SQL queries, and data quality notes.
"""
import os
import sys
from pathlib import Path
import httpx
import pandas as pd
import streamlit as st

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(
    page_title="AI BI Assistant | Sales Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for styling
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .answer-card {
        background: linear-gradient(135deg, #F0FDF4 0%, #E0F2FE 100%);
        border: 1px solid #BAE6FD;
        border-radius: 12px;
        padding: 20px 24px;
        margin: 15px 0 25px 0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    .answer-text {
        font-size: 1.25rem;
        font-weight: 600;
        color: #0F172A;
        line-height: 1.5;
    }
    .badge-rule {
        background-color: #EDE9FE;
        color: #6D28D9;
        font-size: 0.8rem;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
    }
    .badge-llm {
        background-color: #DCFCE7;
        color: #15803D;
        font-size: 0.8rem;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
    }
    .metric-chip {
        display: inline-block;
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 8px 14px;
        margin-right: 10px;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def call_api_ask(question: str) -> dict:
    """Send natural language query to the backend API."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{API_BASE_URL}/ask", json={"question": question})
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 422:
                return {
                    "status": "error",
                    "answer": "Validation Error: Question must be between 1 and 500 characters.",
                }
            elif resp.status_code == 500:
                return {
                    "status": "error",
                    "answer": "The backend server encountered an internal error. Please try again later.",
                }
            else:
                return {
                    "status": "error",
                    "answer": f"Unexpected server response ({resp.status_code}): {resp.text}",
                }
    except httpx.ConnectError:
        return {
            "status": "offline",
            "answer": (
                f"Cannot connect to the backend API at {API_BASE_URL}. "
                "Please make sure the backend service is running (e.g. `uvicorn app.main:app --port 8000`)."
            ),
        }
    except Exception as e:
        return {"status": "error", "answer": f"Network or client error: {e}"}


def get_health_status() -> dict:
    """Fetch backend health and row counts."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{API_BASE_URL}/health")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {"status": "offline"}


# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ System Status")
    health = get_health_status()
    if health.get("status") == "ok":
        st.success("● API Online & Connected")
        st.caption(f"**Total DB Rows:** {health.get('total_rows', 0)}")
        st.caption(f"**Included in BI:** {health.get('included_rows', 0)}")
        st.caption(f"**Excluded Rows:** {health.get('excluded_rows', 0)}")
    else:
        st.error("● API Offline")
        st.caption(f"Target: `{API_BASE_URL}`")
        st.info("Start backend with:\n`uvicorn app.main:app --port 8000`")

    st.markdown("---")
    st.markdown("### 📌 Business Rules Summary")
    st.markdown(
        """
        - **Revenue**: `Quantity × Unit Price - Discount`
        - **Inclusion**: `Completed` orders only, non-zero quantity, valid price & date.
        - **Excluded Rows**: Kept in DB with exclusion reason (auditability). Never deleted.
        - **Currency**: Unspecified in raw data (displayed with standard grouping).
        """
    )
    st.markdown("---")
    st.caption("AI-Assisted BI Assistant | RSG Research GET Assignment")

# Main Content Header
st.markdown('<div class="main-title">Mini AI Business Intelligence Assistant</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Deterministic SQL analytics driven by natural language intent classification.</div>',
    unsafe_allow_html=True,
)

# Preset Questions Buttons
st.markdown("**Quick Example Questions:**")
example_cols = st.columns(5)
preset_clicked = None

examples = [
    ("💰 Total Revenue", "What is the total revenue?"),
    ("🏆 Top Product", "Which product generated the highest revenue?"),
    ("📈 Monthly Trend", "What is the monthly revenue trend?"),
    ("🗺️ Top Region", "Which region generated the highest sales?"),
    ("⚖️ Jan vs Feb", "How did revenue change between January and February 2026?"),
]

for col, (label, query) in zip(example_cols, examples):
    if col.button(label, use_container_width=True):
        preset_clicked = query

# Input area
if "query_input" not in st.session_state:
    st.session_state.query_input = ""

if preset_clicked:
    st.session_state.query_input = preset_clicked

with st.form("ask_form", clear_on_submit=False):
    col1, col2 = st.columns([5, 1])
    with col1:
        user_question = st.text_input(
            "Enter your question about sales data:",
            value=st.session_state.query_input,
            placeholder="e.g. What is the total revenue or Which product generated the highest revenue?",
            label_visibility="collapsed",
        )
    with col2:
        submit = st.form_submit_button("Ask Assistant", use_container_width=True, type="primary")

# Execute query if submitted or preset clicked
active_query = user_question if submit else (preset_clicked if preset_clicked else None)

if active_query:
    with st.spinner("Analyzing query and querying database..."):
        response = call_api_ask(active_query)

    resp_status = response.get("status")
    answer = response.get("answer", "No answer returned.")
    interpreter = response.get("interpreter", "rule_based")
    intent = response.get("intent", "unsupported")

    if resp_status == "offline":
        st.error(f"⚠️ **Backend Offline**: {answer}")
    elif resp_status == "error":
        st.error(f"❌ {answer}")
    elif resp_status == "unsupported":
        st.warning(f"ℹ️ {answer}")
        if "supported_questions" in response:
            st.markdown("**Supported question examples:**")
            for sq in response["supported_questions"]:
                st.markdown(f"- *{sq}*")
    elif resp_status == "ok":
        # Badge for Interpreter
        badge_html = (
            f'<span class="badge-llm">🤖 Interpreter: {interpreter.upper()}</span>'
            if interpreter == "llm"
            else f'<span class="badge-rule">⚡ Interpreter: {interpreter.upper()}</span>'
        )

        st.markdown(
            f"""
            <div class="answer-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-size: 0.85rem; font-weight: 600; color: #475569;">ASSISTANT ANSWER</span>
                    {badge_html}
                </div>
                <div class="answer-text">{answer}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Supporting Data & Visualization
        supporting_data = response.get("supporting_data", [])
        if supporting_data:
            df = pd.DataFrame(supporting_data)

            # Display Monthly Trend Chart if monthly data is available
            if intent in ("monthly_revenue_trend", "revenue_change_between_months") and "order_month" in df.columns:
                st.markdown("### 📊 Monthly Trajectory")
                chart_df = df.copy()
                if "monthly_revenue" in chart_df.columns:
                    chart_df["monthly_revenue"] = pd.to_numeric(chart_df["monthly_revenue"])
                    chart_df = chart_df.sort_values("order_month")
                    st.bar_chart(chart_df.set_index("order_month")["monthly_revenue"])

            st.markdown("### 📋 Supporting Figures")
            # Format numeric columns for display
            display_df = df.copy()
            for col in display_df.columns:
                if "revenue" in col:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "")
                elif "quantity" in col or "count" in col or "units" in col:
                    display_df[col] = display_df[col].apply(lambda x: f"{int(x):,}" if pd.notnull(x) else "")

            st.dataframe(display_df, use_container_width=True, hide_index=True)

        # SQL Inspection Expander
        with st.expander("🔍 SQL Transparency & Query Inspection"):
            st.markdown("**Deterministic SQL Query Template:**")
            sql_used = response.get("sql_used")
            if sql_used:
                st.code(sql_used, language="sql")
                params = response.get("sql_parameters", [])
                st.markdown(f"**Query Parameters:** `{params}`")
                st.caption(
                    "Security Note: The LLM does NOT generate free-form SQL. "
                    "The backend executes fixed, parameterized queries against a read-only SQLite connection."
                )
            else:
                st.info("No database query was executed.")

        # Data Notes Expander
        with st.expander("ℹ️ Data Handling & Quality Notes"):
            notes = response.get("data_notes", {})
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Included Rows in Analytics", notes.get("included_rows", 48))
            with col_b:
                st.metric("Excluded Rows (Audited)", notes.get("excluded_rows", 3))

            st.markdown(f"**Revenue Formula:** `{notes.get('revenue_definition', '')}`")
            st.caption(notes.get("currency_note", "Currency unspecified."))
