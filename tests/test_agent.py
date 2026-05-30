"""Tests for the Agent class."""

from __future__ import annotations

from src.agent import Agent, AgentConfig


def _make_config(**overrides: object) -> AgentConfig:
    """Create a minimal AgentConfig for testing."""
    from src.client import LlmClient

    llm = LlmClient(
        api_key="sk-test",
        base_url="https://test.api.com",
        model="test-model",
        max_tokens=1024,
        temperature=0.7,
        top_p=1.0,
    )
    defaults: dict[str, object] = {
        "llm": llm,
        "system_prompt": "Test system prompt",
        "max_tokens": 1024,
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)  # type: ignore[arg-type]


def test_agent_initialization() -> None:
    """Agent should store agent_id, role, mode, and model correctly."""
    config = _make_config(role="worker", mode="code")
    agent = Agent(agent_id="test-agent-1", config=config)
    assert agent.agent_id == "test-agent-1"
    assert agent.config.role == "worker"
    assert agent.config.mode == "code"
    assert agent.config.llm.model == "test-model"


def test_agent_reset() -> None:
    """Reset should clear messages, tokens, and change_log."""
    config = _make_config()
    agent = Agent(agent_id="reset-test", config=config)
    agent.send_message("Hello", role="user")
    agent.send_message("Hi there", role="assistant")
    assert len(agent.messages) == 2
    agent._input_tokens = 100
    agent._output_tokens = 50
    agent._change_log.append({"tool": "write_file", "path": "test.py"})

    agent.reset()

    assert agent.messages == []
    assert agent._input_tokens == 0
    assert agent._output_tokens == 0
    assert agent._change_log == []


def test_send_message() -> None:
    """Messages should be appended to the buffer."""
    config = _make_config()
    agent = Agent(agent_id="msg-test", config=config)
    agent.send_message("Hello", role="user")
    assert len(agent.messages) == 1
    assert agent.messages[0]["role"] == "user"
    assert agent.messages[0]["content"] == "Hello"

    agent.send_message("Response", role="assistant")
    assert len(agent.messages) == 2
    assert agent.messages[1]["role"] == "assistant"


def test_get_last_assistant_text_string() -> None:
    """Should retrieve the last assistant message with string content."""
    config = _make_config()
    agent = Agent(agent_id="last-text", config=config)
    agent.send_message("User msg", role="user")
    agent.send_message("Assistant reply", role="assistant")
    assert agent.get_last_assistant_text() == "Assistant reply"


def test_get_last_assistant_text_list() -> None:
    """Should merge text blocks from a list content message."""
    config = _make_config()
    agent = Agent(agent_id="last-list", config=config)
    agent.send_message("User msg", role="user")
    agent.messages.append(
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "tool_use", "name": "read_file", "input": {"path": "x.py"}},
                {"type": "text", "text": "World"},
            ],
        }
    )
    result = agent.get_last_assistant_text()
    assert "Hello" in result
    assert "World" in result
    assert "tool_use" not in result  # only text blocks


def test_get_last_assistant_text_empty() -> None:
    """Should return empty string when no assistant messages exist."""
    config = _make_config()
    agent = Agent(agent_id="empty-test", config=config)
    assert agent.get_last_assistant_text() == ""

    # Only user messages
    agent.send_message("User msg", role="user")
    assert agent.get_last_assistant_text() == ""


def test_is_read_only_true() -> None:
    """plan, ask, and observer roles should be read-only."""
    config = _make_config(role="plan")
    agent = Agent(agent_id="ro-plan", config=config)
    assert agent.is_read_only is True

    config2 = _make_config(role="ask")
    agent2 = Agent(agent_id="ro-ask", config=config2)
    assert agent2.is_read_only is True

    config3 = _make_config(role="observer")
    agent3 = Agent(agent_id="ro-observer", config=config3)
    assert agent3.is_read_only is True


def test_is_read_only_false() -> None:
    """code and worker roles should NOT be read-only."""
    config = _make_config(role="code")
    agent = Agent(agent_id="rw-code", config=config)
    assert agent.is_read_only is False

    config2 = _make_config(role="worker")
    agent2 = Agent(agent_id="rw-worker", config=config2)
    assert agent2.is_read_only is False
