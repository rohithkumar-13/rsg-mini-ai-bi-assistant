"""SQL query security guard.

Enforces defense-in-depth validation ensuring queries are strictly read-only single
SELECT statements with no comments, statement chaining, or DDL/DML keywords.
"""
import re

FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "REPLACE",
    "CREATE",
    "TRIGGER",
    "INDEX",
    "EXEC",
    "EXECUTE",
    "VACUUM",
    "GRANT",
    "REVOKE",
}

# Comment patterns (-- comment or /* comment */)
COMMENT_REGEX = re.compile(r"(--|/\*|\*/)")


class SQLSecurityError(ValueError):
    """Raised when a SQL query violates security guardrails."""
    pass


def validate_select_only(sql: str) -> bool:
    """Validate that the given SQL string is a single, safe SELECT query.
    
    Raises SQLSecurityError if:
    - The query is empty or whitespace only
    - It contains SQL comments (-- or /* */)
    - It contains multiple statements or semicolons
    - It contains any DDL/DML mutation keywords
    - It does not start with SELECT
    
    Returns True if valid.
    """
    if not sql or not sql.strip():
        raise SQLSecurityError("SQL query cannot be empty.")

    cleaned = sql.strip()

    # Reject comments
    if COMMENT_REGEX.search(cleaned):
        raise SQLSecurityError("SQL comments are strictly forbidden.")

    # Reject stacked statements / semicolons (except trailing semicolon)
    # Check if semicolon exists and is not just the very last non-whitespace char
    semi_idx = cleaned.find(";")
    if semi_idx != -1 and semi_idx < len(cleaned) - 1:
        raise SQLSecurityError("Stacked statements / multiple queries are strictly forbidden.")

    # Strip optional trailing semicolon for analysis
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    # Extract words/tokens
    tokens = [t.upper() for t in re.findall(r"\b[A-Za-z_]+\b", cleaned)]
    if not tokens:
        raise SQLSecurityError("No valid SQL tokens found in query.")

    # Must start with SELECT
    if tokens[0] != "SELECT":
        raise SQLSecurityError(f"Query must begin with SELECT, found: {tokens[0]}")

    # Check against forbidden keyword set
    for token in tokens:
        if token in FORBIDDEN_KEYWORDS:
            raise SQLSecurityError(f"Forbidden SQL keyword detected: '{token}'")

    return True
