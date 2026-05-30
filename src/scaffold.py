"""Project scaffolding module for creating new projects from templates."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)

# Built-in templates directory
BUILTIN_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
# User custom templates
CUSTOM_TEMPLATES_DIR = Path("templates")


def list_templates() -> list[dict[str, Any]]:
    """List available templates (built-in + custom)."""
    templates: list[dict[str, Any]] = []

    # Scan built-in templates
    if BUILTIN_TEMPLATES_DIR.exists():
        for d in BUILTIN_TEMPLATES_DIR.iterdir():
            if d.is_dir():
                templates.append(
                    {
                        "name": d.name,
                        "builtin": True,
                        "description": _get_template_description(d),
                    }
                )

    # Scan custom templates
    custom_dir = CUSTOM_TEMPLATES_DIR.resolve()
    if custom_dir.exists():
        for d in custom_dir.iterdir():
            if d.is_dir() and d.name not in [t["name"] for t in templates]:
                templates.append(
                    {
                        "name": d.name,
                        "builtin": False,
                        "description": _get_template_description(d),
                    }
                )

    return sorted(templates, key=lambda t: t["name"])


def _get_template_description(template_dir: Path) -> str:
    """Extract description from template README or return default."""
    readme = template_dir / "README.md"
    if readme.exists():
        try:
            content = readme.read_text(encoding="utf-8")
            # First non-empty line after any heading
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    return line[:100]
        except Exception:
            pass
    return ""


def _substitute_variables(content: str, variables: dict[str, str]) -> str:
    """Replace {{variable}} placeholders with actual values."""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return variables.get(key, match.group(0))

    return re.sub(r"\{\{(\w+)\}\}", _replace, content)


def scaffold_project(
    template_name: str,
    project_name: str,
    target_dir: str | None = None,
    variables: dict[str, str] | None = None,
) -> str:
    """Create a new project from a template.

    Args:
        template_name: Name of the template to use
        project_name: Name for the new project
        target_dir: Directory to create the project in (default: current dir)
        variables: Additional {{variables}} to substitute

    Returns:
        Success or error message
    """

    # Find template source
    template_dir = _find_template(template_name)
    if template_dir is None:
        return f"Error: template '{template_name}' not found"

    # Set up target directory
    target = Path(target_dir or os.getcwd()) / project_name
    if target.exists():
        return f"Error: target directory already exists: {target}"

    # Merge variables with defaults
    all_vars: dict[str, str] = {
        "project_name": project_name,
        "package_name": project_name.replace("-", "_").replace(" ", "_"),
    }
    if variables:
        all_vars.update(variables)

    try:
        # Copy template files
        shutil.copytree(template_dir, target)

        # Process all files for variable substitution
        for filepath in target.rglob("*"):
            if filepath.is_file():
                _process_template_file(filepath, all_vars)

        logger.info("Scaffolded project '%s' from template '%s'", project_name, template_name)
        return f"Created project '{project_name}' from '{template_name}' template at {target}"

    except Exception as e:
        # Clean up on failure
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        return f"Error creating project: {e}"


def _find_template(name: str) -> Path | None:
    """Find a template by name (checks built-in then custom)."""
    # Check built-in
    builtin = BUILTIN_TEMPLATES_DIR / name
    if builtin.exists() and builtin.is_dir():
        return builtin

    # Check custom
    custom = CUSTOM_TEMPLATES_DIR.resolve() / name
    if custom.exists() and custom.is_dir():
        return custom

    return None


def _process_template_file(filepath: Path, variables: dict[str, str]) -> None:
    """Process a single template file (substitute variables, rename if needed)."""
    # Substitute in file content
    try:
        content = filepath.read_text(encoding="utf-8")
        new_content = _substitute_variables(content, variables)
        if new_content != content:
            filepath.write_text(new_content, encoding="utf-8")
    except Exception as e:
        logger.debug("Skipping variable substitution in %s: %s", filepath.name, e)

    # Rename file if it contains placeholders
    new_name = _substitute_variables(filepath.name, variables)
    if new_name != filepath.name:
        new_path = filepath.parent / new_name
        filepath.rename(new_path)


def show_template(template_name: str) -> str:
    """Show the structure and description of a template."""
    template_dir = _find_template(template_name)
    if template_dir is None:
        return f"Error: template '{template_name}' not found"

    lines: list[str] = [f"Template: {template_name}"]
    lines.append(f"{'=' * (len(template_name) + 10)}")
    lines.append("")

    for filepath in sorted(template_dir.rglob("*")):
        if filepath.is_file():
            rel = filepath.relative_to(template_dir)
            lines.append(f"  {rel}")

    return "\n".join(lines)
