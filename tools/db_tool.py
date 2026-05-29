"""Database explorer tool for the Coding Agent.

Supports SQLite (built-in), PostgreSQL, and MySQL connections.
Read-only by default; writes require explicit confirmation.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from tools import Tool, ToolContext
from src.logging_config import get_logger

logger = get_logger(__name__)

# DDL statements that modify data — requires confirmation
WRITE_STATEMENTS = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "REPLACE", "GRANT", "REVOKE",
})


def _is_write_query(query: str) -> bool:
    """Check if a SQL query is a write operation."""
    first_word = query.strip().split()[0].upper() if query.strip() else ""
    return first_word in WRITE_STATEMENTS


def _connect_sqlite(db_path: str) -> sqlite3.Connection:
    """Connect to a SQLite database file."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_postgres(host: str, port: int, database: str, user: str, password: str) -> Any:
    """Connect to PostgreSQL."""
    try:
        import psycopg2  # type: ignore[import-untyped]
        conn = psycopg2.connect(
            host=host, port=port, database=database,
            user=user, password=password,
        )
        return conn
    except ImportError:
        raise ImportError("PostgreSQL requires 'psycopg2': pip install psycopg2-binary")


def _connect_mysql(host: str, port: int, database: str, user: str, password: str) -> Any:
    """Connect to MySQL."""
    try:
        import pymysql  # type: ignore[import-untyped]
        conn = pymysql.connect(
            host=host, port=port, database=database,
            user=user, password=password,
        )
        return conn
    except ImportError:
        raise ImportError("MySQL requires 'pymysql': pip install pymysql")


def _format_table_schema(conn: Any, db_type: str) -> str:
    """Get schema information for all tables."""
    from src.utils import green, dim

    if db_type == "sqlite":
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        table_names = [row["name"] for row in cursor.fetchall()]

        result: list[str] = []
        for table in table_names:
            result.append(f"\n{green(table)}")
            cursor = conn.execute(f"PRAGMA table_info('{table}')")
            for col in cursor.fetchall():
                nullable = "NULL" if col["notnull"] == 0 else "NOT NULL"
                default = f" DEFAULT {col['dflt_value']}" if col["dflt_value"] else ""
                pk = " PK" if col["pk"] else ""
                result.append(f"  ├ {col['name']}: {col['type']} {nullable}{default}{pk}")

        return "\n".join(result)
    else:
        # PostgreSQL / MySQL: use information_schema
        cursor = conn.execute("""
            SELECT table_name, column_name, data_type, is_nullable,
                   column_default, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
        """)
        rows = cursor.fetchall()

        tables: dict[str, list[str]] = {}
        for row in rows:
            table_name = row["table_name"]
            col_info = f"  ├ {row['column_name']}: {row['data_type']}"
            if row.get("character_maximum_length"):
                col_info += f"({row['character_maximum_length']})"
            if row.get("is_nullable") == "NO":
                col_info += " NOT NULL"
            if row.get("column_default"):
                col_info += f" DEFAULT {row['column_default']}"
            tables.setdefault(table_name, []).append(col_info)

        result = []
        for table_name, cols in tables.items():
            result.append(f"\n{green(table_name)}")
            result.extend(cols)

        return "\n".join(result)


def execute(args: dict[str, Any], ctx: ToolContext) -> str:
    """Execute a database action."""
    from src.utils import green, bold, dim, yellow, red

    db_type = args.get("type", "sqlite")
    action = args.get("action", "query")
    query = args.get("query", "")

    logger.info("execute: db_type=%s, action=%s, query_len=%d", db_type, action, len(query))

    # Connection parameters
    db_path = args.get("path", "")  # SQLite only
    host = args.get("host", "localhost")
    port = int(args.get("port", 0))
    database = args.get("database", "")
    user = args.get("user", "")
    password = args.get("password", "")

    try:
        # Connect
        if db_type == "sqlite":
            if not db_path:
                return "Error: 'path' required for SQLite databases"
            conn = _connect_sqlite(db_path)
        elif db_type == "postgresql":
            port = port or 5432
            conn = _connect_postgres(host, port, database, user, password)
        elif db_type == "mysql":
            port = port or 3306
            conn = _connect_mysql(host, port, database, user, password)
        else:
            return f"Error: unsupported database type '{db_type}'. Use: sqlite, postgresql, mysql"

        try:
            # Handle actions
            if action == "tables":
                logger.info("Fetching schema for database: %s", database or db_path)
                return f"\n{green(f'Tables in {database or db_path}')}\n{_format_table_schema(conn, db_type)}"

            elif action == "query":
                if not query:
                    return "Error: 'query' required for action=query"

                # Check for write operations
                if _is_write_query(query):
                    logger.warning("Write query detected: %s", query[:100])
                    if not args.get("confirm"):
                        return (
                            f"{yellow('⚠')} Write query detected: {query[:80]}...\n"
                            f"  This query modifies data. Set 'confirm=true' to execute."
                        )

                cursor = conn.execute(query)

                if _is_write_query(query):
                    conn.commit()
                    return f"{green('✓')} Query executed: {cursor.rowcount} row(s) affected"

                # Fetch results
                rows = cursor.fetchmany(50)  # Limit to 50 rows
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                if not rows:
                    return "Query returned no results."

                # Format as table
                result = f"\n  {bold(f'Query Results ({len(rows)} rows)')}"
                result += f"\n  {'─' * 60}"
                result += f"\n  {' │ '.join(columns)}"
                result += f"\n  {'─' * 60}"

                for row in rows:
                    values = [str(c)[:40] if c is not None else "NULL" for c in row]
                    result += f"\n  {' │ '.join(values)}"

                if len(rows) == 50:
                    result += f"\n  {dim('(showing first 50 rows — add LIMIT to your query for more)')}"

                return result

            else:
                return f"Error: unknown action '{action}'. Use: tables, query"

        finally:
            conn.close()

    except ImportError as e:
        logger.error("Database import error: %s", e)
        return f"{red('✗')} {e}"
    except Exception as e:
        logger.error("Database error for %s: %s", db_type, e)
        return f"{red('✗')} Database error: {e}"


# Tool definition
db_tool = Tool(
    name="db",
    description=(
        "Browse databases and run SQL queries. Supports SQLite (built-in), PostgreSQL, and MySQL. "
        "Write queries (INSERT/UPDATE/DELETE) require explicit confirmation."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Database type: sqlite, postgresql, mysql (default: sqlite)",
                "enum": ["sqlite", "postgresql", "mysql"],
            },
            "action": {
                "type": "string",
                "description": "Action: tables (show schema), query (run SQL)",
                "enum": ["tables", "query"],
            },
            "query": {
                "type": "string",
                "description": "SQL query to execute (for action=query)",
            },
            "path": {
                "type": "string",
                "description": "Path to SQLite database file",
            },
            "host": {"type": "string", "description": "Database host (default: localhost)"},
            "port": {"type": "number", "description": "Database port"},
            "database": {"type": "string", "description": "Database name"},
            "user": {"type": "string", "description": "Database user"},
            "password": {"type": "string", "description": "Database password"},
            "confirm": {
                "type": "boolean",
                "description": "Confirm write operations (required for INSERT/UPDATE/DELETE)",
            },
        },
        "required": [],
    },
    execute=execute,
)
