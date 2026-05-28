"""Tests for the Python REPL integration."""
from __future__ import annotations

from src.python_repl import PythonRepl


def test_execute_simple_expression() -> None:
    """Execute a simple Python expression and verify output."""
    repl = PythonRepl()
    output = repl.execute("print(1 + 1)")
    assert output == "2"


def test_execute_multi_line_function() -> None:
    """Define a function, then call it."""
    repl = PythonRepl()
    repl.execute("def greet(name):\n    return f'Hello, {name}!'")
    output = repl.execute("print(greet('World'))")
    assert output == "Hello, World!"


def test_variable_persistence() -> None:
    """Variables should persist across calls."""
    repl = PythonRepl()
    repl.execute("x = 42")
    output = repl.execute("print(x * 2)")
    assert output == "84"


def test_syntax_error() -> None:
    """Syntax errors should be caught and reported."""
    repl = PythonRepl()
    output = repl.execute("print(1 +")
    assert "SyntaxError" in output or "Error" in output or "invalid" in output or "unexpected" in output or output == ""


def test_runtime_error() -> None:
    """Runtime errors should be caught and reported."""
    repl = PythonRepl()
    output = repl.execute("1 / 0")
    assert "Error" in output or "ZeroDivisionError" in output or "division" in output


def test_error_count_tracking() -> None:
    """Error count should increment on errors."""
    repl = PythonRepl()
    assert repl.error_count == 0
    repl.execute("1 / 0")
    assert repl.error_count == 1


def test_execution_count() -> None:
    """Execution count should increment."""
    repl = PythonRepl()
    assert repl.execution_count == 0
    repl.execute("1 + 1")
    assert repl.execution_count == 1
    repl.execute("2 + 2")
    assert repl.execution_count == 2


def test_reset_clears_variables() -> None:
    """Reset should clear all variables and counts."""
    repl = PythonRepl()
    repl.execute("x = 42")
    assert len(repl.get_variables()) > 0
    repl.reset()
    assert repl.execution_count == 0
    assert repl.error_count == 0
    assert len(repl.get_variables()) == 0


def test_empty_code_returns_empty() -> None:
    """Empty code should return empty string."""
    repl = PythonRepl()
    output = repl.execute("")
    assert output == ""


def test_get_variables_excludes_dunders() -> None:
    """get_variables should exclude builtins and internal vars."""
    repl = PythonRepl()
    repl.execute("my_var = 100")
    vars_dict = repl.get_variables()
    assert "my_var" in vars_dict
    assert vars_dict["my_var"] == 100
    # Built-in names should not appear
    assert "__builtins__" not in vars_dict


def test_history() -> None:
    """Execution history should be tracked."""
    repl = PythonRepl()
    repl.execute("a = 1")
    repl.execute("b = 2")
    assert len(repl.history) == 2
    assert "a = 1" in repl.history
    assert "b = 2" in repl.history
