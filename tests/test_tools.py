"""Tests for the tool registry."""

from __future__ import annotations

from pathlib import Path

from tools import Tool, ToolContext, ToolRegistry


def test_register_and_get() -> None:
    def _execute(args: dict[str, object], ctx: ToolContext) -> str:
        return "done"

    registry = ToolRegistry()
    tool = Tool(name="test_tool", description="A test tool", input_schema={}, execute=_execute)
    registry.register(tool)
    assert registry.get("test_tool") is tool
    assert registry.get("nonexistent") is None


def test_get_all() -> None:
    registry = ToolRegistry()
    t1 = Tool(name="t1", description="", input_schema={}, execute=lambda a, c: "")
    t2 = Tool(name="t2", description="", input_schema={}, execute=lambda a, c: "")
    registry.register(t1)
    registry.register(t2)
    assert len(registry.get_all()) == 2


def test_get_read_only() -> None:
    registry = ToolRegistry()
    ro = Tool(name="read_only_tool", description="", input_schema={}, execute=lambda a, c: "", read_only=True)
    rw = Tool(name="read_write_tool", description="", input_schema={}, execute=lambda a, c: "", read_only=False)
    registry.register(ro)
    registry.register(rw)
    ro_tools = registry.get_read_only()
    assert len(ro_tools) == 1
    assert ro_tools[0].name == "read_only_tool"


def test_to_anthropic_tools() -> None:
    registry = ToolRegistry()
    t = Tool(name="my_tool", description="Does stuff", input_schema={"type": "object"}, execute=lambda a, c: "")
    registry.register(t)
    result = registry.to_anthropic_tools()
    assert len(result) == 1
    assert result[0]["name"] == "my_tool"
    assert result[0]["description"] == "Does stuff"
    assert result[0]["input_schema"] == {"type": "object"}


def test_to_anthropic_tools_read_only() -> None:
    registry = ToolRegistry()
    registry.register(Tool(name="ro", description="", input_schema={}, execute=lambda a, c: "", read_only=True))
    registry.register(Tool(name="rw", description="", input_schema={}, execute=lambda a, c: "", read_only=False))
    ro_tools = registry.to_anthropic_tools(read_only=True)
    assert len(ro_tools) == 1
    assert ro_tools[0]["name"] == "ro"


def test_tool_context() -> None:
    ctx = ToolContext(working_directory="/test/dir")
    assert ctx.working_directory == "/test/dir"


def test_all_tools_have_explicit_read_only() -> None:
    """Every registered tool should have an explicit read_only flag."""
    tools_dir = Path(__file__).resolve().parent.parent / "tools"
    for f in sorted(tools_dir.iterdir()):
        if f.suffix != ".py" or f.name in ("__init__.py",):
            continue
        # Skip files that don't define a Tool (helpers without Tool definition)
        content = f.read_text(encoding="utf-8")
        if "_tool = Tool(" not in content:
            continue
        assert "read_only=" in content, (
            f"Tool file {f.name} is missing explicit read_only flag. "
            f"Add read_only=True or read_only=False to the Tool() definition."
        )


# ── Bash tool env var access tests ────────────────────────────────────────────


class TestBashToolEnvVarDetection:
    """Verify detection of sensitive env var access in bash commands."""

    def test_detect_echo_api_key(self) -> None:
        """Echo of ANTHROPIC_API_KEY should be detected."""
        from tools.bash_tool import _check_for_sensitive_env_access
        result = _check_for_sensitive_env_access("echo $ANTHROPIC_API_KEY")
        assert result is not None
        assert "ANTHROPIC_API_KEY" in result

    def test_detect_echo_braces(self) -> None:
        """Echo with ${} syntax should be detected."""
        from tools.bash_tool import _check_for_sensitive_env_access
        result = _check_for_sensitive_env_access("echo ${ANTHROPIC_API_KEY}")
        assert result is not None

    def test_no_false_positive_on_safe_vars(self) -> None:
        """Safe environment variables should not be flagged."""
        from tools.bash_tool import _check_for_sensitive_env_access
        assert _check_for_sensitive_env_access("echo $HOME") is None
        assert _check_for_sensitive_env_access("echo $PATH") is None
        assert _check_for_sensitive_env_access("echo $USER") is None

    def test_no_false_positive_on_normal_commands(self) -> None:
        """Normal commands without env var access should not be flagged."""
        from tools.bash_tool import _check_for_sensitive_env_access
        assert _check_for_sensitive_env_access("ls -la") is None
        assert _check_for_sensitive_env_access("python -m pytest tests/") is None
        assert _check_for_sensitive_env_access("git status") is None
