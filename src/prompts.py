"""Prompt library for the Coding Agent.

Provides built-in prompt templates and save/load/list functionality
for custom prompt templates stored as Markdown files in the prompts/ directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)

PROMPTS_DIR = "prompts"

BUILTIN_PROMPTS: dict[str, str] = {
    "refactor": """Refactor the following code to improve readability, maintainability, and performance. Follow best practices for the language/framework. Do not change external behavior or public API signatures.""",
    "fix-bug": """There is a bug in the following code. Identify the root cause and provide a fix. Explain what was wrong and how the fix addresses it. Consider edge cases.""",
    "add-feature": """Add the following feature to the codebase. Follow existing patterns and conventions. Update any relevant tests or documentation as needed.""",
    "write-tests": """Write comprehensive tests for the following code. Cover:
- Happy path
- Edge cases
- Error conditions
- Input validation

Use the existing test framework and conventions in the project.""",
    "code-review": """Review the following code for:
- Correctness
- Performance
- Security
- Maintainability
- Style and conventions
- Error handling

Provide specific, actionable feedback with code examples where appropriate.""",
}


@dataclass
class PromptTemplate:
    """Represents a prompt template."""

    name: str
    content: str
    is_builtin: bool = False
    filepath: str | None = None


def _ensure_prompts_dir(working_directory: str) -> Path:
    """Ensure the prompts/ directory exists."""
    prompts_dir = Path(working_directory) / PROMPTS_DIR
    prompts_dir.mkdir(parents=True, exist_ok=True)
    return prompts_dir


def list_prompts(working_directory: str) -> list[PromptTemplate]:
    """Return built-in + custom prompts from the prompts/ directory."""
    prompts: list[PromptTemplate] = []

    # Built-in prompts
    for name, content in BUILTIN_PROMPTS.items():
        prompts.append(PromptTemplate(name=name, content=content, is_builtin=True))

    # Custom prompts from prompts/ directory
    prompts_dir = _ensure_prompts_dir(working_directory)
    for f in sorted(prompts_dir.iterdir()):
        if f.suffix != ".md":
            continue
        try:
            content = f.read_text(encoding="utf-8").strip()
            if content:
                prompts.append(
                    PromptTemplate(
                        name=f.stem,
                        content=content,
                        is_builtin=False,
                        filepath=str(f),
                    )
                )
        except OSError, UnicodeDecodeError:
            continue

    return prompts


def save_prompt(name: str, content: str, working_directory: str) -> str:
    """Save a custom prompt as a .md file. Returns the file path."""
    safe_name = "".join(c for c in name.strip() if c.isalnum() or c in "-_.")
    if not safe_name:
        safe_name = "custom-prompt"
    prompts_dir = _ensure_prompts_dir(working_directory)
    filepath = prompts_dir / f"{safe_name}.md"
    filepath.write_text(content.strip(), encoding="utf-8")
    logger.info("Prompt saved: name=%s, file=%s", safe_name, filepath)
    return str(filepath)


def load_prompt(name: str, working_directory: str) -> PromptTemplate | None:
    """Load a prompt by name. Checks custom first, then built-in."""
    # Check custom prompts first
    prompts_dir = _ensure_prompts_dir(working_directory)
    safe_name = "".join(c for c in name.strip() if c.isalnum() or c in "-_.")
    custom_path = prompts_dir / f"{safe_name}.md"
    if custom_path.is_file():
        try:
            content = custom_path.read_text(encoding="utf-8").strip()
            return PromptTemplate(
                name=safe_name,
                content=content,
                is_builtin=False,
                filepath=str(custom_path),
            )
        except OSError, UnicodeDecodeError:
            pass

    # Check built-in
    if name in BUILTIN_PROMPTS:
        return PromptTemplate(name=name, content=BUILTIN_PROMPTS[name], is_builtin=True)

    return None
