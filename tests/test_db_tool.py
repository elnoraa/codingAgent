"""Tests for database tool security."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tools import Tool, ToolContext
from tools.db_tool import execute, _is_write_query, _format_table_schema


from collections.abc import Generator


@pytest.fixture
def tmp_db() -> Generator[str, None, None]:
    """Create a temporary SQLite database with a test table."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@test.com')")
        conn.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@test.com')")
        conn.commit()
        conn.close()
        yield db_path


@pytest.fixture
def ctx() -> Generator[ToolContext, None, None]:
    yield ToolContext(working_directory="/tmp")


class TestFormatTableSchema:
    """Verify table schema formatting is safe from SQL injection."""

    def test_format_table_schema_no_injection(self, tmp_db: str) -> None:
        """PRAGMA table_info should use parameterized query, not f-string."""
        conn = sqlite3.connect(tmp_db)
        schema = _format_table_schema(conn, "sqlite")
        conn.close()

        assert "users" in schema
        assert "id" in schema
        assert "name" in schema
        assert "email" in schema

    def test_format_table_schema_with_special_chars(self) -> None:
        """Table names with special characters should be handled safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "CREATE TABLE \"users'; DROP TABLE users; --\" (id INTEGER)"
                )
                conn.commit()

                # This should not raise an error (which would indicate SQL injection)
                try:
                    schema = _format_table_schema(conn, "sqlite")
                except Exception as exc:
                    pytest.fail(f"_format_table_schema raised unexpectedly: {exc}")
            finally:
                conn.close()

            # Verify the table is still there (the dangerous name wasn't executed)
            conn2 = sqlite3.connect(db_path)
            try:
                tables = conn2.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                assert len(tables) >= 1  # Our table still exists
            finally:
                conn2.close()

            # The dangerous table name should appear in the schema (displayed safely)
            assert "DROP" in schema


class TestIsWriteQuery:
    """Verify write query detection."""

    def test_detects_insert(self) -> None:
        assert _is_write_query("INSERT INTO users VALUES (1, 'a')")

    def test_detects_update(self) -> None:
        assert _is_write_query("UPDATE users SET name='b' WHERE id=1")

    def test_detects_delete(self) -> None:
        assert _is_write_query("DELETE FROM users WHERE id=1")

    def test_detects_drop(self) -> None:
        assert _is_write_query("DROP TABLE users")

    def test_detects_create(self) -> None:
        assert _is_write_query("CREATE TABLE test (id INT)")

    def test_detects_alter(self) -> None:
        assert _is_write_query("ALTER TABLE users ADD COLUMN age INT")

    def test_detects_truncate(self) -> None:
        assert _is_write_query("TRUNCATE TABLE users")

    def test_detects_replace(self) -> None:
        assert _is_write_query("REPLACE INTO users VALUES (1, 'a')")

    def test_detects_grant(self) -> None:
        assert _is_write_query("GRANT SELECT ON users TO alice")

    def test_detects_revoke(self) -> None:
        assert _is_write_query("REVOKE SELECT ON users FROM alice")

    def test_returns_false_for_select(self) -> None:
        assert not _is_write_query("SELECT * FROM users")

    def test_returns_false_for_pragma(self) -> None:
        assert not _is_write_query("PRAGMA table_info('users')")

    def test_returns_false_for_explain(self) -> None:
        assert not _is_write_query("EXPLAIN SELECT * FROM users")

    def test_empty_string_returns_false(self) -> None:
        assert not _is_write_query("")

    def test_whitespace_only_returns_false(self) -> None:
        assert not _is_write_query("   ")


class TestExecute:
    """Integration tests for db_tool execute."""

    def test_execute_select(self, ctx: ToolContext, tmp_db: str) -> None:
        """SELECT queries should return results."""
        result = execute({
            "type": "sqlite",
            "action": "query",
            "query": "SELECT * FROM users ORDER BY id",
            "path": tmp_db,
        }, ctx)
        assert "Alice" in result
        assert "Bob" in result
        assert "Query Results" in result

    def test_execute_tables(self, ctx: ToolContext, tmp_db: str) -> None:
        """Tables action should show schema."""
        result = execute({
            "type": "sqlite",
            "action": "tables",
            "path": tmp_db,
        }, ctx)
        assert "users" in result

    def test_write_query_needs_confirm(self, ctx: ToolContext, tmp_db: str) -> None:
        """Write queries should require confirm=True."""
        result = execute({
            "type": "sqlite",
            "action": "query",
            "query": "DELETE FROM users WHERE id=1",
            "path": tmp_db,
            "confirm": False,
        }, ctx)
        assert "confirm" in result.lower() or "write" in result.lower()

    def test_write_query_with_confirm(self, ctx: ToolContext, tmp_db: str) -> None:
        """Write queries with confirm=True should execute."""
        result = execute({
            "type": "sqlite",
            "action": "query",
            "query": "DELETE FROM users WHERE id=1",
            "path": tmp_db,
            "confirm": True,
        }, ctx)
        assert "row(s) affected" in result

    def test_execute_missing_path(self, ctx: ToolContext) -> None:
        """Missing path for SQLite should return error."""
        result = execute({
            "type": "sqlite",
            "action": "tables",
            "path": "",
        }, ctx)
        assert "Error" in result or "required" in result.lower()

    def test_execute_bad_query(self, ctx: ToolContext, tmp_db: str) -> None:
        """Invalid SQL should return an error, not crash."""
        result = execute({
            "type": "sqlite",
            "action": "query",
            "query": "SELECT invalid_sql FROM nowhere",
            "path": tmp_db,
        }, ctx)
        assert "Error" in result or "error" in result.lower()

    def test_execute_empty_query(self, ctx: ToolContext, tmp_db: str) -> None:
        """Empty query should return error."""
        result = execute({
            "type": "sqlite",
            "action": "query",
            "query": "",
            "path": tmp_db,
        }, ctx)
        assert "Error" in result or "required" in result.lower()

    def test_execute_unknown_action(self, ctx: ToolContext, tmp_db: str) -> None:
        """Unknown action should return error."""
        result = execute({
            "type": "sqlite",
            "action": "nonexistent",
            "path": tmp_db,
        }, ctx)
        assert "Error" in result or "unknown" in result.lower()
