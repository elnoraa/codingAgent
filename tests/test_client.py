"""Tests for the LLM client and model routing modules."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.client import SENSITIVE_PARAMS, LlmClient, _summarize_args
from src.model_routing import ModelConfig, MultiModelClient

# ── _summarize_args tests ─────────────────────────────────────────────────


class TestSummarizeArgs:
    """Verify tool argument summarization with sensitive-data redaction."""

    def test_normal_string_included(self) -> None:
        result = _summarize_args({"path": "/tmp/test.py"})  # noqa: S108
        assert "path=/tmp/test.py" in result

    def test_long_string_truncated(self) -> None:
        long_str = "x" * 100
        result = _summarize_args({"content": long_str})
        assert result.endswith("...")
        assert len(result) < 150  # truncated

    def test_non_string_uses_repr(self) -> None:
        result = _summarize_args({"count": 42, "enabled": True})
        assert "count=42" in result
        assert "enabled=True" in result

    def test_sensitive_params_redacted(self) -> None:
        result = _summarize_args({"api_key": "sk-abcdef123456"})
        assert "api_key=****" in result
        assert "abcdef" not in result

    def test_password_redacted(self) -> None:
        result = _summarize_args({"password": "supersecret"})
        assert "password=****" in result

    def test_token_redacted(self) -> None:
        result = _summarize_args({"token": "ghp_abc123def456"})
        assert "token=****" in result

    def test_secret_redacted(self) -> None:
        result = _summarize_args({"secret": "my-secret-value"})
        assert "secret=****" in result

    def test_multiple_params_mixed(self) -> None:
        result = _summarize_args({"path": "file.txt", "api_key": "sk-test", "mode": "code"})
        assert "path=file.txt" in result
        assert "api_key=****" in result
        assert "mode=code" in result

    def test_empty_dict(self) -> None:
        result = _summarize_args({})
        assert result == ""


# ── SENSITIVE_PARAMS ───────────────────────────────────────────────────────


class TestSensitiveParams:
    """Verify the SENSITIVE_PARAMS frozenset contains expected keys."""

    def test_contains_password(self) -> None:
        assert "password" in SENSITIVE_PARAMS

    def test_contains_api_key(self) -> None:
        assert "api_key" in SENSITIVE_PARAMS

    def test_contains_token(self) -> None:
        assert "token" in SENSITIVE_PARAMS

    def test_contains_secret(self) -> None:
        assert "secret" in SENSITIVE_PARAMS

    def test_contains_aliases(self) -> None:
        assert "passwd" in SENSITIVE_PARAMS
        assert "auth_token" in SENSITIVE_PARAMS
        assert "access_token" in SENSITIVE_PARAMS
        assert "private_key" in SENSITIVE_PARAMS
        assert "apikey" in SENSITIVE_PARAMS

    def test_does_not_contain_safe_param(self) -> None:
        assert "path" not in SENSITIVE_PARAMS
        assert "content" not in SENSITIVE_PARAMS
        assert "name" not in SENSITIVE_PARAMS


# ── LlmClient tests ───────────────────────────────────────────────────────


class TestLlmClientInit:
    """Verify LlmClient initialization."""

    def test_stores_parameters(self) -> None:
        with patch("src.client.Anthropic") as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            client = LlmClient(
                api_key="sk-test-key",
                base_url="https://api.test.com",
                model="test-model",
                max_tokens=4096,
                temperature=0.5,
                top_p=0.9,
            )
            assert client.model == "test-model"
            assert client.max_tokens == 4096
            assert client.temperature == 0.5
            assert client.top_p == 0.9

    def test_creates_anthropic_client(self) -> None:
        with patch("src.client.Anthropic") as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            LlmClient(
                api_key="sk-test-key",
                base_url="https://api.test.com",
                model="test-model",
                max_tokens=4096,
            )
            mock_anthropic.assert_called_once_with(
                api_key="sk-test-key",
                base_url="https://api.test.com",
            )

    def test_on_budget_check_default_none(self) -> None:
        with patch("src.client.Anthropic") as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            client = LlmClient(
                api_key="sk-test-key",
                base_url="https://api.test.com",
                model="test-model",
                max_tokens=4096,
            )
            assert client.on_budget_check is None

    def test_default_temperature_and_top_p(self) -> None:
        with patch("src.client.Anthropic") as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            client = LlmClient(
                api_key="sk-test-key",
                base_url="https://api.test.com",
                model="test-model",
                max_tokens=4096,
            )
            assert client.temperature == 0.7
            assert client.top_p == 1.0


# ── MultiModelClient tests ────────────────────────────────────────────────


class TestMultiModelClient:
    """Verify multi-model routing."""

    def make_client(self) -> MultiModelClient:
        return MultiModelClient(
            api_key="sk-test-key",
            base_url="https://api.test.com",
            default_config=ModelConfig(
                model="default-model",
                max_tokens=4096,
                temperature=0.7,
                top_p=1.0,
                description="Default",
            ),
            mode_configs={
                "plan": ModelConfig(
                    model="plan-model",
                    max_tokens=8192,
                    temperature=0.3,
                    top_p=1.0,
                    description="Planning mode",
                ),
                "ask": ModelConfig(
                    model="ask-model",
                    max_tokens=2048,
                    temperature=0.5,
                    top_p=1.0,
                    description="Ask mode",
                ),
            },
            read_only_config=ModelConfig(
                model="readonly-model",
                max_tokens=1024,
                temperature=0.5,
                top_p=1.0,
                description="Read-only mode",
            ),
        )

    def test_default_config_when_mode_not_found(self) -> None:
        mc = self.make_client()
        with patch("src.client.Anthropic"):
            llm = mc.get_client_for_mode("code")
            assert llm.model == "default-model"
            assert llm.max_tokens == 4096

    def test_mode_specific_config(self) -> None:
        mc = self.make_client()
        with patch("src.client.Anthropic"):
            llm = mc.get_client_for_mode("plan")
            assert llm.model == "plan-model"
            assert llm.max_tokens == 8192
            assert llm.temperature == 0.3

    def test_another_mode_config(self) -> None:
        mc = self.make_client()
        with patch("src.client.Anthropic"):
            llm = mc.get_client_for_mode("ask")
            assert llm.model == "ask-model"
            assert llm.max_tokens == 2048

    def test_read_only_config(self) -> None:
        mc = self.make_client()
        with patch("src.client.Anthropic"):
            llm = mc.get_client_for_mode("code", read_only=True)
            assert llm.model == "readonly-model"
            assert llm.max_tokens == 1024

    def test_read_only_not_configured_falls_back(self) -> None:
        mc = MultiModelClient(
            api_key="sk-test-key",
            base_url="https://api.test.com",
            default_config=ModelConfig(model="default", max_tokens=4096),
            read_only_config=None,
        )
        with patch("src.client.Anthropic"):
            llm = mc.get_client_for_mode("code", read_only=True)
            assert llm.model == "default"

    def test_current_model_property(self) -> None:
        mc = self.make_client()
        assert mc.current_model == "default-model"
        with patch("src.client.Anthropic"):
            mc.get_client_for_mode("plan")
        assert mc.current_model == "plan-model"

    def test_current_max_tokens_property(self) -> None:
        mc = self.make_client()
        assert mc.current_max_tokens == 4096
        with patch("src.client.Anthropic"):
            mc.get_client_for_mode("ask")
        assert mc.current_max_tokens == 2048
