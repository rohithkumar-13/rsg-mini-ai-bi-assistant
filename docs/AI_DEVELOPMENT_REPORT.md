# AI-Assisted Development Report

**Author**: Graduate Engineer Trainee Candidate  
**Project**: Mini AI Business Intelligence Assistant  
**Challenge**: RSG Research Private Limited - GET Selection Challenge  
**Date**: October 2026  

---

## 1. AI Tools & Environment Used

During the design and implementation of this application, I utilized:
- **Google Antigravity**: Primary agentic AI coding environment, providing pair programming, workspace inspection, terminal execution, and automated testing capabilities.
- **Foundation LLM**: Advanced reasoning model powering code synthesis, edge-case generation, and design critique.
- **Runtime LLM (Optional Integration)**: `google-genai` SDK configuring Google Gemini (`gemini-2.5-flash`) for natural language intent classification.
- **Deterministic Python Runtime**: Python 3.10 with SQLite, FastAPI, Pydantic, Pandas, and Streamlit.

---

## 2. Phase-by-Phase AI Utilization & Prompts

### Phase 1: Workspace Inspection & Data Profiling
- **Approach**: Before writing any project code, I used the agent to read the assignment requirements from `RSG AI Assisted Development Challenge - GET.docx` and profile `ai_bi_assistant_sales_data - GET.csv`.
- **What Was Prompted**: *"Inspect the CSV with Python. Check null counts, date formats, status distributions, discount ranges, and independently compute total revenue, top products, top regions, and monthly trends."*
- **Outcome**: Verified that there are 51 rows, 48 valid for analytics, and 3 excluded (`TXN0033` returned, `TXN0034` zero quantity, `TXN0051` missing price). Ground-truth numbers matched the benchmark targets exactly.

### Phase 2: Architecture & Safety Guardrails Design
- **Approach**: To guarantee zero hallucinations and zero SQL injection, I prompted for an architecture that eliminates free-form Text-to-SQL.
- **What Was Prompted**: *"Design a deterministic architecture where the LLM is restricted solely to classifying user intents into an enum and extracting month parameters into a Pydantic schema. All SQL must be fixed parameterized templates executed on a read-only SQLite connection."*
- **Outcome**: Formulated the `sql_guard.validate_select_only()` function, read-only SQLite URI (`mode=ro`), `PRAGMA query_only = ON`, and the numeric-narrative verification filter.

### Phase 3: Implementation & Dual-Engine Interpretation
- **Approach**: Developed the offline-first rule-based interpreter alongside the optional Gemini SDK integration.
- **What Was Prompted**: *"Write a rule-based synonym and regex parser that supports varied phrasing for the five business queries. Build an automatic fallback so that if Gemini is disabled or fails, the rule-based engine answers seamlessly."*
- **Outcome**: The assistant works out-of-the-box with zero API keys and zero network calls, while gracefully upgrading when an API key is provided.

### Phase 4: Test Suite & Edge Cases
- **Approach**: Instructed the agent to write a comprehensive test suite rather than minimal tests.
- **What Was Prompted**: *"Generate pytest tests covering loader idempotence, synthetic corrupted CSVs, benchmark calculations, safe division by zero, SQL injection attempts, and Pydantic validation."*
- **Outcome**: Created 61 automated tests covering unit, edge, security, and integration levels.

---

## 3. Real Problems Encountered & How They Were Debugged

During this build, I encountered four real technical issues. Here is the honest record of symptoms, root causes, and fixes:

### Problem 1: PowerShell Parsing Error with Python One-Liners
- **Symptom**: Running `python -c "..."` commands in Windows PowerShell failed with `ParserError: The string is missing the terminator: '` and f-string backslash syntax errors.
- **Root Cause**: PowerShell treats quotes and backslashes differently from Unix bash, corrupting inner quotes in multi-line inline strings.
- **Fix**: Replaced brittle inline CLI commands by creating dedicated scratch scripts (e.g. `scratch/profile_data.py` and `scratch/verify_live_api.py`) and executing them with `.venv\Scripts\python.exe <script>`.

### Problem 2: Browser Automation Binary Download Blocked
- **Symptom**: When the browser subagent attempted to launch Playwright to capture a screenshot of the Streamlit UI, it failed with a 404 download error from `playwright.azureedge.net`.
- **Root Cause**: Playwright attempted to download browser binaries at runtime in an environment with restricted external binary downloads.
- **Fix**: Recognized the environment constraint. Instead of failing, I verified the Streamlit service directly via HTTP requests (`GET http://localhost:8501/` returning status 200), verified the backend API with live end-to-end HTTP calls, and relied on the comprehensive 61-test pytest suite.

### Problem 3: Regex Mismatch on "Best Performing Sales Region"
- **Symptom**: `tests/test_interpreter.py::test_rule_based_paraphrase_coverage[best performing sales region-top_region_by_sales]` failed with `AssertionError: assert <QueryIntent.UNSUPPORTED> == <QueryIntent.TOP_REGION_BY_SALES>`.
- **Root Cause**: The initial regex `\b(which|what|top|best|highest|leading)\s+region\b` required the word "region" immediately after "best", failing on compound adjective phrases like "best performing sales region".
- **Fix**: Updated `app/interpreter.py` to use non-capturing optional modifier groups:
  ```python
  re.search(r"\b(which|what|top|best|highest|leading)\s+(?:(?:performing|selling)\s+)?(?:(?:sales|revenue)\s+)?region\b", q)
  ```
  Re-running pytest confirmed 100% of tests passed.

### Problem 4: TestClient Deprecation Warning with HTTPX
- **Symptom**: Pytest displayed a Starlette deprecation warning regarding HTTPX integration with TestClient.
- **Root Cause**: FastAPI and Starlette recently updated test client conventions in newer package releases.
- **Fix**: Verified test functionality remained 100% intact and documented the warning in the test report.

---

## 4. What Was Verified Manually vs. By AI

| Area | Verified by AI | Verified Manually by Author |
| :--- | :--- | :--- |
| **Data Profiling** | Pandas script execution & row counts | Cross-referenced CSV rows in Excel against table notes in assignment docx |
| **Business Rules** | Unit test assertion generation | Hand-calculated line revenues (e.g. `TXN0004: 6 * 9500 - 500 = 56,500`) |
| **SQL Security** | Injection test payloads (`DROP TABLE`, etc.) | Checked SQLite connection settings and verified database file persistence |
| **API Endpoints** | Pytest TestClient automation | Real HTTP calls against live server `http://127.0.0.1:8000` via python script |
| **UI Rendering** | Streamlit code generation | Verified Streamlit process startup, terminal logs, and HTTP 200 health status |

---

## 5. Current State: What Works, What Doesn't, and Why

### What Works:
1. **Official Data Loading & Audit**: Exactly 51 rows processed, 48 included, 3 excluded with clear audit reasons (`returned`, `zero_quantity`, `missing_unit_price`). Original rows are stored intact.
2. **All 5 Business Questions**: All 5 queries return 100% correct, verified benchmark figures.
3. **Dual Interpretation**: Seamless offline operation via regex/synonym engine; fully validated Gemini integration when configured.
4. **SQL Security Guard**: Complete defense-in-depth preventing SQL injection, mutation queries, comments, and stacked statements.
5. **FastAPI & Streamlit UI**: Both services run concurrently and communicate smoothly over HTTP.
6. **Automated Test Suite**: 61/61 tests passing.

### What Doesn't / Constraints:
1. **Playwright Browser Screenshot**: Browser driver binary download was blocked in the local environment; UI verification was confirmed via HTTP endpoints.
2. **Arbitrary Ad-Hoc Analytics**: Questions outside the 5 supported intents (e.g., *"What is the average transaction value in the West region?"*) return guided unsupported messages rather than dynamically generated SQL. This is an intentional safety design decision.

---

## 6. What Would Be Improved with Another Day of Work

1. **Multi-Turn Conversational Memory**: Introduce session-based conversational state so users can ask follow-ups (e.g., *"What about in the North?"* after asking for top products).
2. **Grammar-Constrained Text-to-SQL**: Implement constrained decoding using libraries like Outlines or Guidance to generate arbitrary safe `SELECT` statements constrained strictly to the SQLite schema.
3. **Glossary-Driven RAG**: Index KPI definitions, business terms, and data dictionaries into an embedded vector store to automatically clarify ambiguous queries.
4. **Automated CI/CD**: Set up a GitHub Actions workflow that executes `pytest -v` and linting on every commit.
5. **Containerization**: Provide a single multi-stage `Dockerfile` and `docker-compose.yml` for unified backend and frontend orchestration.

---

## 7. Interview Preparation: 10 Likely Questions & Sharp Answers

### Q1: Why did you choose intent classification instead of free-form Text-to-SQL?
**Answer**: In commercial BI applications, accuracy is non-negotiable. Free-form Text-to-SQL introduces hallucination risks, calculation inconsistencies (e.g., how discounts are subtracted), and SQL injection vulnerabilities. By extracting structured intents into Pydantic models and executing fixed, parameterized SQL queries, we guarantee 100% mathematical correctness, zero hallucinations, and total injection prevention.

### Q2: How does the system guarantee that numbers in the response are not hallucinated?
**Answer**: All numbers displayed in the answer card and supporting data originate directly from the database execution engine. Furthermore, our `verify_narrative_numbers` function uses regex tokenization to verify that every number mentioned in an explanation string exists within the computed database facts. If any unverified number is detected, the narrative is discarded and our deterministic template is displayed.

### Q3: How do you prevent SQL injection and destructive database operations?
**Answer**: Through four layers of defense-in-depth:
1. User input is never concatenated into SQL; all queries use parameterized `?` placeholders.
2. SQLite connections for analytics are opened in read-only mode (`file:...mode=ro`) with `PRAGMA query_only = ON`.
3. `sql_guard.validate_select_only()` inspects query strings to reject semicolons, comments, and mutation keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ATTACH`, etc.).
4. The system validates all intent parameters against strict Pydantic regex patterns (`YYYY-MM`).

### Q4: How are data quality issues handled in the raw sales data?
**Answer**: Non-destructively. Rather than dropping or silently modifying bad records, all 51 rows are saved in SQLite. Excluded records are assigned `is_included = 0` and an explicit `exclusion_reason` (e.g. `returned` for `TXN0033`, `zero_quantity` for `TXN0034`, and `missing_unit_price` for `TXN0051`). Missing prices are never imputed.

### Q5: What assumption was made regarding the discount column?
**Answer**: We verified in row `TXN0004` (Quantity=6, Price=9500, Discount=500, Gross=57000) that `Discount_amount` represents the total discount for the entire transaction line ($57,000 - 500 = 56,500$), rather than a per-unit discount. This assumption is encapsulated in `app/rules.py` and can be changed in a single line if business policies evolve.

### Q6: How does the app operate without an API key or internet access?
**Answer**: The system defaults to `LLM_PROVIDER=none`, utilizing our `rule_based_interpret` engine. It applies regex matching, synonym maps, and natural month parsers to classify questions and extract parameters entirely in local Python memory.

### Q7: How are mathematical edge cases like division by zero handled?
**Answer**: When comparing revenue between two months where the base month revenue is 0, dividing by zero would cause a fatal crash. Our analytics engine explicitly catches this, reporting the absolute revenue change and returning `percentage_change: null` with an explanatory note.

### Q8: How does this project relate to Generative AI and Agentic AI?
**Answer**: This project demonstrates the fundamental principle of **Agentic Tool Use & Guardrails**: using Generative AI for its cognitive strength (understanding ambiguous human language) while strictly delegating execution and computation to deterministic tools (SQL engines and math libraries).

### Q9: What is "Vectorless RAG" and how does this project exemplify it?
**Answer**: Traditional RAG converts text into dense vector embeddings and searches across vector databases. **Vectorless RAG** retrieves ground truth from structured, relational, or graph databases using deterministic queries. In our architecture, the user's natural language question is mapped to a structured intent that retrieves facts from SQLite, synthesizing answers without vector stores.

### Q10: How would you scale this architecture for enterprise deployment?
**Answer**: I would place FastAPI behind an NGINX reverse proxy, run SQLite in WAL mode or migrate to read-replica PostgreSQL, introduce Redis caching for frequent aggregations, and wrap the intent interpreter in a multi-agent framework (like Google ADK or LangGraph) to orchestrate complex analytical workflows.
