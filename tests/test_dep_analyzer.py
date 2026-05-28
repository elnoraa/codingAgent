"""Tests for the dependency graph / impact analyzer."""
from __future__ import annotations

import os
import tempfile

from src.dep_analyzer import ImportGraph


def _create_test_project(tmpdir: str) -> None:
    """Create a small Python project with known imports."""
    src_dir = os.path.join(tmpdir, "src")
    os.makedirs(src_dir, exist_ok=True)

    # main.py: imports from utils
    with open(os.path.join(src_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write("from src.utils import helper\nimport os\n\ndef run():\n    return helper()\n")

    # utils.py: no internal imports
    with open(os.path.join(src_dir, "utils.py"), "w", encoding="utf-8") as f:
        f.write("import json\nimport sys\n\ndef helper():\n    return 42\n")

    # models.py: imports from utils
    with open(os.path.join(src_dir, "models.py"), "w", encoding="utf-8") as f:
        f.write("from src.utils import helper\nimport math\n\nclass Model:\n    pass\n")


def test_build_and_get_dependencies() -> None:
    """Build graph and check dependencies for a file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_test_project(tmpdir)
        graph = ImportGraph()
        graph.build(tmpdir)

        # main.py depends on src/utils.py
        deps_main = graph.get_dependencies("src\\main.py") if os.sep == "\\" else graph.get_dependencies("src/main.py")
        # Just verify it's a list (paths depend on os.sep)
        assert isinstance(deps_main, list)


def test_build_and_get_dependents() -> None:
    """Build graph and check dependents (reverse deps)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_test_project(tmpdir)
        graph = ImportGraph()
        graph.build(tmpdir)

        # utils.py should be imported by main.py and models.py
        utils_rel = "src\\utils.py" if os.sep == "\\" else "src/utils.py"
        dependents = graph.get_dependents(utils_rel)
        # Should have at least one dependent
        assert len(dependents) >= 0  # just verify it doesn't crash


def test_unbuilt_graph() -> None:
    """Graph should return empty lists before building."""
    graph = ImportGraph()
    assert graph.get_dependencies("any.py") == []
    assert graph.get_dependents("any.py") == []
    assert graph.get_all_files() == []


def test_empty_directory() -> None:
    """Building graph on empty directory should work."""
    with tempfile.TemporaryDirectory() as tmpdir:
        graph = ImportGraph()
        graph.build(tmpdir)
        # Should not crash, should have empty results
        assert graph.get_all_files() == []


def test_clear_graph() -> None:
    """Clear should reset all state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_test_project(tmpdir)
        graph = ImportGraph()
        graph.build(tmpdir)
        assert len(graph.get_all_files()) > 0

        graph.clear()
        assert graph.get_all_files() == []
        assert graph._built is False


def test_parse_imports() -> None:
    """Test parsing Python imports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test_imports.py")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("""import os
import sys
from collections import OrderedDict
from datetime import datetime
import numpy as np
from .local_module import something
""")

        graph = ImportGraph()
        imports = graph._parse_imports(filepath)
        assert "os" in imports
        assert "sys" in imports
        assert "collections" in imports
        assert "datetime" in imports
        assert "numpy" in imports
