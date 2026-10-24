# System Architecture & Technical Design

This document details the architectural blueprint, data model, component interactions, and engineering trade-offs of the Mini AI Business Intelligence Assistant.

---

## 1. High-Level Component Architecture

The application adopts a modular, tiered architecture separating user presentation, API routing, AI intent extraction, database security guardrails, and deterministic analytics execution.

```mermaid
graph TD
    subgraph Presentation Layer
        UI[Streamlit Web UI<br/>ui/streamlit_app.py]
    end

    subgraph API Gateway
        API[FastAPI Service<br/>app/main.py]
    end

    subgraph Orchestration & Intelligence Layer
        Service[Service Orchestrator<br/>app/service.py]
        Interp[Query Interpreter<br/>app/interpreter.py]
        LLM[Google Gemini SDK<br/>Optional Cloud]
        RuleEngine[Rule-Based Parser<br/>Offline Engine]
        Verifier[Narrative Fact Verifier<br/>app/analytics.py]
    end

    subgraph Security & Guardrail Layer
        SQLGuard[SQL Guard<br/>app/sql_guard.py]
        DBConn[Read-Only SQLite Connection<br/>PRAGMA query_only=ON]
    end

    subgraph Data & Analytics Layer
        Analytics[Parameterized SQL Templates<br/>app/analytics.py]
        DB[(SQLite Database<br/>data/sales.db)]
        Loader[CSV Loader & Validator<br/>app/loader.py]
        SourceCSV[Source CSV<br/>data/ai_bi_assistant_sales_data.csv]
    end

    UI -->|HTTP POST /ask| API
    API --> Service
    Service --> Interp
    Interp -.->|If LLM_PROVIDER=gemini| LLM
    Interp -->|Default & Fallback| RuleEngine
    Service --> Analytics
    Analytics --> SQLGuard
    SQLGuard --> DBConn
    DBConn --> DB
    Analytics --> Verifier
    Loader -->|ETL Writer Connection| DB
    SourceCSV --> Loader
```

---

## 2. Request-Flow Sequence Diagram

The following sequence diagram illustrates the lifecycle of a business user's query:

```mermaid
sequenceDiagram
    autonumber
    actor User as Business Stakeholder
    participant UI as Streamlit UI
    participant API as FastAPI (/ask)
    participant Svc as Service Layer
    participant Interp as Interpreter Layer
    participant Guard as SQL Guard
    participant DB as SQLite (Read-Only)
    participant Verifier as Fact Verifier

    User->>UI: Types query or clicks quick button
    UI->>API: POST /ask {question: "..."}
    API->>Svc: process_question(question)
    
    rect rgb(240, 248, 255)
        note right of Svc: 1. AI Intent Classification
        Svc->>Interp: interpret_question(cleaned_q)
        alt LLM Configured & Healthy
            Interp->>Interp: Call Gemini API (JSON schema)
        else LLM Disabled or Times Out
            Interp->>Interp: Rule-based synonym & regex match
        end
        Interp-->>Svc: InterpreterResult(intent, parameters)
    end

    alt Intent is UNSUPPORTED
        Svc-->>API: Status 200 (status="unsupported", guided questions)
        API-->>UI: Friendly guidance message
    else Intent is SUPPORTED
        rect rgb(245, 255, 245)
            note right of Svc: 2. Deterministic SQL Execution
            Svc->>Guard: validate_select_only(sql_template)
            Guard-->>Svc: Query validated (safe single SELECT)
            Svc->>DB: Execute parameterized query (bound params)
            DB-->>Svc: Raw tabular results
        end

        rect rgb(255, 250, 240)
            note right of Svc: 3. Narrative Verification & Synthesis
            Svc->>Verifier: verify_narrative_numbers(narrative, db_facts)
            alt All numbers exist in DB facts
                Verifier-->>Svc: Narrative approved
            else Unverified numbers detected
                Verifier-->>Svc: Discard narrative, use deterministic template
            end
        end

        Svc-->>API: Structured response payload
        API-->>UI: HTTP 200 OK (JSON)
        UI-->>User: Render Answer Card, Trend Chart, Table, SQL Inspector
    end
```

---

## 3. Database Schema

The sales data is persisted in a relational SQLite table designed to preserve auditability and facilitate fast query execution:

```sql
CREATE TABLE sales (
    transaction_id TEXT PRIMARY KEY,
    order_date TEXT,          -- ISO YYYY-MM-DD
    order_month TEXT,         -- ISO YYYY-MM (for fast group-bys)
    product TEXT,             -- Normalized trimmed product name
    category TEXT,            -- Product category
    region TEXT,              -- Sales region (North, South, East, West)
    sales_channel TEXT,       -- Online / Retail
    quantity INTEGER,         -- Transaction units (NULL if missing)
    unit_price REAL,          -- Price per unit (NULL if missing, never imputed)
    discount_amount REAL,     -- Line discount amount
    status TEXT,              -- Original status (Completed, Returned, etc.)
    line_revenue REAL,        -- Calculated as (quantity * unit_price - discount_amount)
    is_included INTEGER NOT NULL, -- 1 = included in BI analytics, 0 = excluded
    exclusion_reason TEXT     -- Rationale for exclusion (e.g. 'returned', 'zero_quantity')
);

CREATE INDEX idx_sales_order_month ON sales(order_month);
CREATE INDEX idx_sales_product ON sales(product);
CREATE INDEX idx_sales_region ON sales(region);
CREATE INDEX idx_sales_is_included ON sales(is_included);
```

---

## 4. Architectural Decisions & Trade-Offs

### 1. Intent Classification vs. Free-Form Text-to-SQL
- **The Dilemma**: Many LLM applications allow the model to freely draft SQL queries directly from user text.
- **The Risk**: Text-to-SQL models frequently hallucinate column names, apply incorrect joins, fail on nuanced business definitions (such as whether discount is per-unit or per-line), and expose the system to catastrophic injection vulnerabilities.
- **The Decision**: We restrict the AI's role strictly to **Intent Extraction and Parameter Parsing** (producing validated JSON). Fixed, audited parameterized SQL queries written by engineers execute the calculations.
- **The Trade-Off**: Decreases arbitrary question flexibility, but achieves **100% mathematical correctness, zero hallucination of figures, and zero SQL injection risk**.

### 2. Physical Separation of Database Connections
- **The Decision**: The system maintains two distinct SQLite connection factories:
  1. `get_writer_connection()`: Used exclusively during ETL initialization by `loader.py`.
  2. `get_readonly_connection()`: Used exclusively by the analytics service. Configured with URI `file:...mode=ro` and engine pragma `PRAGMA query_only = ON`.
- **The Trade-Off**: Minor overhead of opening separate connections, but establishes ironclad isolation: the analytics layer physically cannot alter data.

### 3. Non-Destructive Audit Trail vs. Dropping Bad Rows
- **The Decision**: In raw transaction data, records like `TXN0033` (Returned), `TXN0034` (Quantity = 0), and `TXN0051` (Missing Unit Price) are invalid for revenue calculations. Instead of discarding them during load time, all 51 rows are saved. Excluded records are flagged with `is_included = 0` and an explicit `exclusion_reason`.
- **The Trade-Off**: Requires filtering `WHERE is_included = 1` on every query, but delivers enterprise-grade data auditability. Stakeholders can inspect why specific rows were omitted via the `/data-quality` endpoint.

### 4. Deterministic Tie-Breaking
- **The Decision**: When querying for "top product" or "top region", ties in revenue could result in non-deterministic ordering across query runs. The queries enforce secondary alphabetical sorting:
  `ORDER BY total_revenue DESC, product ASC LIMIT 1`.
- **The Benefit**: Ensures reproducible and predictable responses.

### 5. Offline Rule-Based Engine as Primary & Fallback
- **The Decision**: We implemented a regex and synonym pattern matcher (`rule_based_interpret`) as the foundation. The LLM is an optional enhancement.
- **The Trade-Off**: Complex queries outside the defined patterns require expanding the regex library, but the application functions reliably with **zero internet, zero API keys, and zero external costs**.
