"""Tests for write-path enforcement — all file operations must stay within the working directory."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.tools import ToolContext
from src.utils import validate_write_path

# ── Test the core validation function ─────────────────────────────────────


def test_valid_path_within_working_dir() -> None:
    """A path inside the working directory is valid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "subdir", "file.txt")
        assert validate_write_path(path, tmpdir) is None


def test_valid_path_is_working_dir_itself() -> None:
    """The working directory itself passed as a direct path is valid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        assert validate_write_path(tmpdir, tmpdir) is None


def test_valid_subdirectory_path() -> None:
    """A subdirectory path is valid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = os.path.join(tmpdir, "subdir")
        os.makedirs(sub)
        assert validate_write_path(sub, tmpdir) is None


def test_invalid_path_parent_directory() -> None:
    """A path outside using '..' should be rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outside = os.path.join(tmpdir, "..", "outside.txt")
        result = validate_write_path(outside, tmpdir)
        assert result is not None
        assert "outside the working directory" in result


def test_invalid_path_absolute_different_location() -> None:
    """An absolute path outside the working directory should be rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = validate_write_path(tmpdir + "_nonexistent", tmpdir)
        assert result is not None
        assert "outside the working directory" in result


def test_invalid_path_sibling_directory() -> None:
    """A path to a sibling directory should be rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sibling = os.path.join(tmpdir, "..", "sibling", "file.txt")
        result = validate_write_path(sibling, tmpdir)
        assert result is not None
        assert "outside the working directory" in result


def test_path_up_then_back_inside() -> None:
    """A path that goes up then back inside (e.g., ../working_dir/file.txt) is valid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dir_name = os.path.basename(tmpdir)
        parent = os.path.dirname(tmpdir)
        valid = os.path.join(parent, dir_name, "file.txt")
        assert validate_write_path(valid, tmpdir) is None


# ── Test ToolContext convenience method ──────────────────────────────────


def test_tool_context_validate_write_path() -> None:
    """ToolContext.validate_write_path() should delegate correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)
        valid_path = os.path.join(tmpdir, "valid.txt")
        invalid_path = os.path.join(tmpdir, "..", "outside.txt")
        assert ctx.validate_write_path(valid_path) is None
        assert ctx.validate_write_path(invalid_path) is not None
        result = ctx.validate_write_path(invalid_path)
        assert result is not None
        assert "outside the working directory" in result


# ── Test individual tool enforcement ─────────────────────────────────────


def test_write_file_enforces_working_directory() -> None:
    """write_file should reject paths outside the working directory."""
    from src.tools.write_file import execute as write_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        # Valid path
        valid = os.path.join(tmpdir, "test.txt")
        result = write_execute({"path": valid, "content": "hello"}, ctx)
        assert result.startswith("Successfully wrote"), f"Expected success, got: {result}"
        assert os.path.isfile(valid)

        # Invalid path (outside)
        invalid = os.path.join(tmpdir, "..", "outside.txt")
        result2 = write_execute({"path": invalid, "content": "bad"}, ctx)
        assert result2.startswith("Error:"), f"Expected error, got: {result2}"
        assert "outside the working directory" in result2


def test_edit_file_enforces_working_directory() -> None:
    """edit_file should reject paths outside the working directory."""
    from src.tools.edit_file import execute as edit_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        # Path outside should be rejected immediately (file won't exist either)
        invalid = os.path.join(tmpdir, "..", "outside.txt")
        result = edit_execute({"path": invalid, "oldText": "a", "newText": "b"}, ctx)
        assert "outside the working directory" in result


def test_rename_file_enforces_working_directory() -> None:
    """rename_file should reject moves outside the working directory."""
    from src.tools.rename_file import execute as rename_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        # Create a source file
        src = os.path.join(tmpdir, "source.txt")
        Path(src).write_text("content")

        # Try to move it outside
        dst = os.path.join(tmpdir, "..", "outside.txt")
        result = rename_execute({"source": src, "destination": dst, "git_move": False}, ctx)
        assert "outside the working directory" in result
        # Source should remain intact
        assert os.path.isfile(src)


def test_replace_in_files_enforces_working_directory() -> None:
    """replace_in_files should reject search directories outside the working directory."""
    from src.tools.replace_in_files import execute as replace_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        invalid_dir = os.path.join(tmpdir, "..", "somewhere")
        result = replace_execute({"oldText": "foo", "newText": "bar", "path": invalid_dir}, ctx)
        assert "outside the working directory" in result


def test_bash_tool_enforces_working_directory_via_workdir() -> None:
    """bash tool should validate that workdir is within the working directory."""
    from src.tools.bash_tool import execute as bash_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        # Invalid workdir
        result = bash_execute({"command": "echo hi", "workdir": os.path.join(tmpdir, "..")}, ctx)
        assert "outside the working directory" in result


def test_bash_tool_blocks_redirect_outside() -> None:
    """bash tool should block commands that redirect output outside the working directory."""
    from src.tools.bash_tool import execute as bash_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        # Try to write outside with redirect
        result = bash_execute({"command": f"echo test > {tmpdir}/../outside.txt"}, ctx)
        assert "Error: Command blocked" in result, f"Expected block, got: {result}"


def test_bash_tool_blocks_mv_outside() -> None:
    """bash tool should block mv commands targeting outside the working directory."""
    from src.tools.bash_tool import execute as bash_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        # Create a file
        src = os.path.join(tmpdir, "test.txt")
        Path(src).write_text("data")

        result = bash_execute({"command": f"mv {src} {tmpdir}/../moved.txt"}, ctx)
        assert "Error: Command blocked" in result, f"Expected block, got: {result}"
        assert os.path.isfile(src)  # Original should remain


def test_bash_tool_allows_normal_commands() -> None:
    """Normal commands within the working directory should work fine."""
    from src.tools.bash_tool import execute as bash_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)
        result = bash_execute({"command": "echo hello world", "workdir": tmpdir}, ctx)
        assert "hello world" in result
        assert not result.startswith("Error:")


def test_python_tool_blocks_open_outside() -> None:
    """python tool should block open() calls that write outside the working directory."""
    from src.tools.python_tool import _execute_python

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        # Try to write outside
        code = f"with open(r'{tmpdir}/../evil.txt', 'w') as f: f.write('bad')"
        result = _execute_python({"code": code}, ctx)
        assert "PermissionError" in result or "outside the working directory" in result


def test_python_tool_allows_normal_code() -> None:
    """Normal Python code should work without interference."""
    from src.tools.python_tool import _execute_python

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)
        result = _execute_python({"code": "result = 1 + 1"}, ctx)
        assert "Error" not in result


def test_git_tools_enforce_working_directory() -> None:
    """Git tools with a path parameter should validate it."""
    from src.tools.git_status import execute as status_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        # Initialize a git repo inside the working dir (so the tool works)
        import subprocess

        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)

        # Valid path should work
        result = status_execute({"path": tmpdir}, ctx)
        assert "On branch" in result

        # Invalid path should fail
        result2 = status_execute({"path": os.path.join(tmpdir, "..")}, ctx)
        assert "outside the working directory" in result2


def test_undo_tool_enforces_working_directory() -> None:
    """undo tool revert should validate path is within working directory."""
    from src.tools.undo_tool import _execute as undo_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(
            working_directory=tmpdir,
            file_snapshots={},
        )

        # Invalid path
        invalid = os.path.join(tmpdir, "..", "outside.txt")
        result = undo_execute({"action": "revert", "path": invalid}, ctx)
        assert "outside the working directory" in result


def test_diff_tool_enforces_working_directory() -> None:
    """diff tool should validate path is within the working directory."""
    from src.tools.diff_tool import execute as diff_execute

    with tempfile.TemporaryDirectory() as tmpdir:
        ctx = ToolContext(working_directory=tmpdir)

        invalid = os.path.join(tmpdir, "..")
        result = diff_execute({"path": invalid}, ctx)
        assert "outside the working directory" in result


# ── Atomic write-path validation tests ─────────────────────────────


class TestAtomicWritePathValidation:
    """Verify that the atomic write-path validator detects symlink escapes
    even when a symlink is created between the initial check and the write."""

    def test_atomic_validation_detects_symlink_escape(self) -> None:
        """validate_write_path_atomic should detect a symlink pointing outside."""
        from src.utils import validate_write_path_atomic

        _check_symlink_support()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a symlink inside workdir pointing outside
            outside = os.path.join(tmpdir, "..", "outside.txt")
            symlink_path = os.path.join(tmpdir, "evil_link")
            os.symlink(outside, symlink_path)

            # The atomic check should catch it
            result = validate_write_path_atomic(symlink_path, tmpdir)
            assert result is not None
            assert "outside the working directory" in result

    def test_atomic_validation_allows_normal_path(self) -> None:
        """validate_write_path_atomic should allow paths inside workdir."""
        from src.utils import validate_write_path_atomic

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "normal_file.txt")
            result = validate_write_path_atomic(path, tmpdir)
            assert result is None

    def test_atomic_validation_rejects_absolute_outside(self) -> None:
        """validate_write_path_atomic should reject absolute paths outside."""
        from src.utils import validate_write_path_atomic

        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a different temp dir that's outside our workdir
            import tempfile as _tf

            other_dir = _tf.mkdtemp()
            try:
                result = validate_write_path_atomic(other_dir, tmpdir)
                assert result is not None
            finally:
                import shutil

                shutil.rmtree(other_dir, ignore_errors=True)

    def test_write_file_atomic_check_blocks_created_symlink(self) -> None:
        """write_file should re-check path right before the write, catching a
        symlink created after the initial validation."""
        from src.tools.write_file import execute as write_execute

        _check_symlink_support()

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = ToolContext(working_directory=tmpdir)

            # First, create a legitimate subdirectory
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)

            # The path we're writing to
            target = os.path.join(subdir, "output.txt")

            # Replace the subdirectory with a symlink pointing outside
            os.rmdir(subdir)
            outside_target = os.path.join(tmpdir, "..", "outside.txt")
            os.symlink(outside_target, subdir)

            # The write should be blocked because the subdir is now a symlink
            result = write_execute({"path": target, "content": "test"}, ctx)
            assert "outside the working directory" in result
            assert "Error" in result

    def test_edit_file_atomic_check_blocks_created_symlink(self) -> None:
        """edit_file should re-check path right before the write."""
        from src.tools.edit_file import execute as edit_execute

        _check_symlink_support()

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = ToolContext(working_directory=tmpdir)

            # Create a file inside
            filepath = os.path.join(tmpdir, "test.txt")
            Path(filepath).write_text("original content")

            # Replace it with a symlink pointing outside
            os.remove(filepath)
            outside_target = os.path.join(tmpdir, "..", "outside.txt")
            os.symlink(outside_target, filepath)

            # The edit should be blocked
            result = edit_execute({"path": filepath, "oldText": "original", "newText": "modified"}, ctx)
            assert "outside the working directory" in result or "Error" in result


def _check_symlink_support() -> None:
    """Check if the OS supports creating symlinks. Skip test if not."""
    if os.name == "nt":
        import pytest

        try:
            test_link = os.path.join(tempfile.mkdtemp(), "_symlink_test")
            os.symlink(__file__, test_link)
            os.remove(test_link)
        except OSError:
            pytest.skip("Symlink creation not supported (requires admin on Windows)")
