"""Tests for the project scaffolding module."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.scaffold import (
    _find_template,
    _substitute_variables,
    scaffold_project,
    list_templates,
    show_template,
)


# ── _substitute_variables tests ───────────────────────────────────────────


class TestSubstituteVariables:
    """Verify template variable substitution."""

    def test_replaces_variable(self) -> None:
        result = _substitute_variables("Hello {{name}}!", {"name": "World"})
        assert result == "Hello World!"

    def test_unknown_variable_unchanged(self) -> None:
        result = _substitute_variables("Hello {{unknown}}!", {"name": "World"})
        assert result == "Hello {{unknown}}!"

    def test_multiple_variables(self) -> None:
        result = _substitute_variables(
            "{{a}} and {{b}}",
            {"a": "foo", "b": "bar"},
        )
        assert result == "foo and bar"

    def test_empty_string(self) -> None:
        result = _substitute_variables("", {"x": "y"})
        assert result == ""

    def test_no_placeholders(self) -> None:
        result = _substitute_variables("plain text", {"x": "y"})
        assert result == "plain text"

    def test_project_name_substitution(self) -> None:
        result = _substitute_variables(
            "Project: {{project_name}}",
            {"project_name": "my-app"},
        )
        assert result == "Project: my-app"


# ── list_templates tests ──────────────────────────────────────────────────


class TestListTemplates:
    """Verify template listing."""

    def test_empty_when_no_templates_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Point both template dirs at non-existent locations
            with patch("src.scaffold.BUILTIN_TEMPLATES_DIR", Path(tmp) / "nonexistent"):
                with patch("src.scaffold.CUSTOM_TEMPLATES_DIR", Path(tmp) / "custom"):
                    result = list_templates()
                    assert result == []


# ── scaffold_project tests ────────────────────────────────────────────────


class TestScaffoldProject:
    """Verify project scaffolding."""

    def test_error_missing_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.scaffold.BUILTIN_TEMPLATES_DIR", Path(tmp) / "templates"):
                result = scaffold_project("nonexistent", "myproject", target_dir=tmp)
                assert "Error" in result
                assert "not found" in result

    def test_error_target_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Create a template dir
            templates_dir = Path(tmp) / "templates" / "mytemplate"
            templates_dir.mkdir(parents=True)
            (templates_dir / "readme.md").write_text("template", encoding="utf-8")

            # Create the target dir so it already exists
            target = Path(tmp) / "existing_project"
            target.mkdir()

            with patch("src.scaffold.BUILTIN_TEMPLATES_DIR", Path(tmp) / "templates"):
                result = scaffold_project("mytemplate", "existing_project", target_dir=tmp)
                assert "Error" in result
                assert "already exists" in result

    def test_scaffold_creates_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Create a template dir with a file
            templates_dir = Path(tmp) / "templates" / "myapp"
            templates_dir.mkdir(parents=True)
            (templates_dir / "README.md").write_text(
                "# {{project_name}}\n\nWelcome!", encoding="utf-8"
            )

            with patch("src.scaffold.BUILTIN_TEMPLATES_DIR", Path(tmp) / "templates"):
                result = scaffold_project("myapp", "test-project", target_dir=tmp)
                assert "Created project" in result

                # Verify the project was created
                project_dir = Path(tmp) / "test-project"
                assert project_dir.exists()
                readme = project_dir / "README.md"
                assert readme.exists()
                content = readme.read_text(encoding="utf-8")
                assert "test-project" in content

    def test_substitutes_filename(self) -> None:
        """Should rename files with {{variable}} in the filename."""
        with tempfile.TemporaryDirectory() as tmp:
            # Template dir with a file that has placeholder in name
            templates_dir = Path(tmp) / "templates" / "lib"
            templates_dir.mkdir(parents=True)
            (templates_dir / "{{package_name}}.py").write_text(
                "version = '1.0'", encoding="utf-8"
            )

            with patch("src.scaffold.BUILTIN_TEMPLATES_DIR", Path(tmp) / "templates"):
                result = scaffold_project("lib", "my-lib", target_dir=tmp)
                assert "Created project" in result

                project_dir = Path(tmp) / "my-lib"
                expected_file = project_dir / "my_lib.py"  # package name replaces hyphens
                assert expected_file.exists(), f"Expected {expected_file} to exist"
                assert expected_file.read_text(encoding="utf-8") == "version = '1.0'"

    def test_extra_variables(self) -> None:
        """Custom variables should be merged with defaults."""
        with tempfile.TemporaryDirectory() as tmp:
            templates_dir = Path(tmp) / "templates" / "app"
            templates_dir.mkdir(parents=True)
            (templates_dir / "main.py").write_text(
                "# {{project_name}} by {{author}}", encoding="utf-8"
            )

            with patch("src.scaffold.BUILTIN_TEMPLATES_DIR", Path(tmp) / "templates"):
                result = scaffold_project(
                    "app", "my-app", target_dir=tmp,
                    variables={"author": "Test User"},
                )
                assert "Created project" in result

                main_py = Path(tmp) / "my-app" / "main.py"
                content = main_py.read_text(encoding="utf-8")
                assert "Test User" in content
                assert "my-app" in content


# ── show_template tests ───────────────────────────────────────────────────


class TestShowTemplate:
    """Verify template display."""

    def test_error_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.scaffold.BUILTIN_TEMPLATES_DIR", Path(tmp) / "templates"):
                result = show_template("nonexistent")
                assert "Error" in result


# ── _find_template tests ──────────────────────────────────────────────────


class TestFindTemplate:
    """Verify template lookup."""

    def test_not_found_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.scaffold.BUILTIN_TEMPLATES_DIR", Path(tmp) / "templates"):
                result = _find_template("nonexistent")
                assert result is None
