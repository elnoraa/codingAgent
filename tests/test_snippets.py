"""Tests for the snippet manager module."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.snippets import (
    delete_snippet,
    list_snippets,
    load_snippet,
    save_snippet,
)


@pytest.fixture(autouse=True)
def _patch_snippets_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect snippets directory to a temp directory for test isolation."""
    snippets_dir = tmp_path / "snippets"
    snippets_dir.mkdir()
    import src.snippets as snip_mod

    monkeypatch.setattr(snip_mod, "SNIPPETS_DIR", snippets_dir)


def test_save_and_list_snippet() -> None:
    """Save a snippet, then list it, verifying it appears in the listing."""
    result = save_snippet("hello-world", 'print("Hello, World!")')
    assert result is True

    snippets = list_snippets()
    assert len(snippets) == 1
    assert snippets[0]["name"] == "hello-world"
    assert snippets[0]["size"] == 22


def test_load_snippet() -> None:
    """Save and load a snippet, verifying content matches."""
    content = "# A test snippet\ndef foo(): pass"
    save_snippet("test-func", content)
    loaded = load_snippet("test-func")
    assert loaded == content


def test_load_nonexistent_snippet() -> None:
    """Loading a snippet that doesn't exist returns None."""
    loaded = load_snippet("does-not-exist")
    assert loaded is None


def test_delete_snippet() -> None:
    """Save a snippet, delete it, then verify it's gone."""
    save_snippet("to-delete", "some content")
    assert load_snippet("to-delete") is not None

    deleted = delete_snippet("to-delete")
    assert deleted is True
    assert load_snippet("to-delete") is None


def test_delete_nonexistent_snippet() -> None:
    """Deleting a snippet that doesn't exist returns False."""
    assert delete_snippet("ghost") is False


def test_save_empty_name() -> None:
    """Saving with an empty name returns False."""
    assert save_snippet("", "content") is False
    assert save_snippet("   ", "content") is False


def test_list_empty() -> None:
    """Listing snippets when none exist returns an empty list."""
    snippets = list_snippets()
    assert snippets == []


def test_snippet_with_description() -> None:
    """Snippet starting with # line uses that line as description."""
    save_snippet("described", "# My description\nactual code here")
    snippets = list_snippets()
    assert len(snippets) == 1
    assert snippets[0]["description"] == "My description"


def test_multiple_snippets() -> None:
    """Multiple snippets are listed in alphabetical order."""
    save_snippet("z-last", "z")
    save_snippet("a-first", "a")
    save_snippet("m-middle", "m")
    snippets = list_snippets()
    assert [s["name"] for s in snippets] == ["a-first", "m-middle", "z-last"]


def test_save_special_chars() -> None:
    """Snippets with special characters in name are saved correctly."""
    name = "my-snippet-v2"
    content = "x = 1\n"
    assert save_snippet(name, content) is True
    loaded = load_snippet(name)
    assert loaded == content
