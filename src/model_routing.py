"""Multi-model routing support for the Coding Agent.

Provides ``ModelConfig`` and ``MultiModelClient`` for switching between
different LLM models based on mode (code/plan/ask) or other routing strategies.

Extracted from ``src/client.py`` to give model routing its own module
(Single Responsibility Principle).
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import LlmClient


@dataclass
class ModelConfig:
    """Configuration for a single model."""

    model: str
    max_tokens: int = 8192
    temperature: float = 0.7
    top_p: float = 1.0
    description: str = ""


class MultiModelClient:
    """Client that can switch between multiple models based on routing strategy."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        default_config: ModelConfig,
        mode_configs: dict[str, ModelConfig] | None = None,
        read_only_config: ModelConfig | None = None,
        strategy: str = "mode",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.default_config = default_config
        self.mode_configs = mode_configs or {}
        self.read_only_config = read_only_config
        self.strategy = strategy
        self._current_config: ModelConfig = default_config

    def get_client_for_mode(self, mode: str, read_only: bool = False) -> LlmClient:
        """Get an LlmClient configured for the given mode."""
        if read_only and self.read_only_config:
            config = self.read_only_config
        else:
            config = self.mode_configs.get(mode, self.default_config)

        self._current_config = config
        return LlmClient(
            api_key=self.api_key,
            base_url=self.base_url,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
        )

    @property
    def current_model(self) -> str:
        return self._current_config.model

    @property
    def current_max_tokens(self) -> int:
        return self._current_config.max_tokens
