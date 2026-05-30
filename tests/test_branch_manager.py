"""Tests for conversation branching."""

from __future__ import annotations

import time

from src.branch_manager import Branch, BranchManager

# ── Branch dataclass tests ────────────────────────────────────────────────


class TestBranch:
    """Verify the Branch dataclass."""

    def test_fields(self) -> None:
        now = time.time()
        branch = Branch(
            name="test-branch",
            parent="main",
            created_at=now,
            messages=[{"role": "user", "content": "hello"}],
            description="A test branch",
        )
        assert branch.name == "test-branch"
        assert branch.parent == "main"
        assert branch.created_at == now
        assert branch.messages == [{"role": "user", "content": "hello"}]
        assert branch.description == "A test branch"

    def test_message_count(self) -> None:
        branch = Branch(
            name="test",
            parent="main",
            created_at=time.time(),
            messages=[{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
        )
        assert branch.message_count == 2

    def test_message_count_empty(self) -> None:
        branch = Branch(
            name="test",
            parent="main",
            created_at=time.time(),
            messages=[],
        )
        assert branch.message_count == 0

    def test_age_seconds(self) -> None:
        branch = Branch(
            name="test",
            parent="main",
            created_at=time.time(),
            messages=[],
        )
        age = branch.age
        assert age.endswith("s ago")
        assert "0s ago" in age or "1s ago" in age  # just created

    def test_age_minutes(self) -> None:
        branch = Branch(
            name="test",
            parent="main",
            created_at=time.time() - 120,  # 2 minutes ago
            messages=[],
        )
        age = branch.age
        assert age.endswith("m ago")

    def test_age_hours(self) -> None:
        branch = Branch(
            name="test",
            parent="main",
            created_at=time.time() - 7200,  # 2 hours ago
            messages=[],
        )
        age = branch.age
        assert age.endswith("h ago")

    def test_default_description(self) -> None:
        branch = Branch(
            name="test",
            parent="main",
            created_at=time.time(),
            messages=[],
        )
        assert branch.description == ""


# ── BranchManager tests ───────────────────────────────────────────────────


class TestBranchManagerInit:
    """Verify BranchManager initialization."""

    def test_creates_main_branch(self) -> None:
        bm = BranchManager()
        assert "main" in bm._branches
        assert bm.active_branch == "main"

    def test_active_messages_returns_main(self) -> None:
        bm = BranchManager()
        assert bm.active_messages == []

    def test_with_initial_messages(self) -> None:
        msgs: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
        bm = BranchManager(initial_messages=msgs)
        assert bm.active_messages == msgs
        # Should be a copy, not the same list
        assert bm.active_messages is not msgs


class TestBranchManagerFork:
    """Verify forking behavior."""

    def test_fork_creates_new_branch(self) -> None:
        bm = BranchManager()
        result = bm.fork("experiment", "Testing a feature")
        assert result is True
        assert "experiment" in bm._branches

    def test_fork_returns_false_if_name_exists(self) -> None:
        bm = BranchManager()
        result = bm.fork("main")
        assert result is False

    def test_fork_deep_copies_messages(self) -> None:
        initial: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
        bm = BranchManager(initial_messages=initial)
        bm.fork("copy")
        # Modify original
        bm.active_messages.append({"role": "user", "content": "world"})
        # Forked branch should still have only 1 message
        forked = bm._branches["copy"]
        assert len(forked.messages) == 1

    def test_fork_sets_parent(self) -> None:
        bm = BranchManager()
        bm.fork("child")
        assert bm._branches["child"].parent == "main"

    def test_fork_default_description(self) -> None:
        bm = BranchManager()
        bm.fork("child")
        forked = bm._branches["child"]
        assert "Fork from main" in forked.description


class TestBranchManagerSwitch:
    """Verify branch switching."""

    def test_switch_to_existing(self) -> None:
        bm = BranchManager()
        bm.fork("other")
        result = bm.switch("other")
        assert result is True
        assert bm.active_branch == "other"

    def test_switch_to_nonexistent(self) -> None:
        bm = BranchManager()
        result = bm.switch("nonexistent")
        assert result is False
        assert bm.active_branch == "main"

    def test_switch_changes_active_messages(self) -> None:
        bm = BranchManager()
        initial: list[dict[str, object]] = [{"role": "user", "content": "initial"}]
        bm.active_messages = initial
        bm.fork("branch-b")
        # Switch to forked branch and set different messages
        bm.switch("branch-b")
        branch_b_msgs: list[dict[str, object]] = [{"role": "user", "content": "on branch b"}]
        bm.active_messages = branch_b_msgs
        # Switch back — main's messages should be the original
        bm.switch("main")
        assert bm.active_messages == initial


class TestBranchManagerDelete:
    """Verify branch deletion."""

    def test_cannot_delete_main(self) -> None:
        bm = BranchManager()
        result = bm.delete("main")
        assert result is False

    def test_cannot_delete_active(self) -> None:
        bm = BranchManager()
        bm.fork("other")
        bm.switch("other")
        result = bm.delete("other")
        assert result is False

    def test_can_delete_other_branch(self) -> None:
        bm = BranchManager()
        bm.fork("other")
        result = bm.delete("other")
        assert result is True
        assert "other" not in bm._branches

    def test_delete_nonexistent(self) -> None:
        bm = BranchManager()
        result = bm.delete("nonexistent")
        assert result is False


class TestBranchManagerActiveMessages:
    """Verify the active_messages setter."""

    def test_setter_updates_branch(self) -> None:
        bm = BranchManager()
        new_msgs: list[dict[str, object]] = [{"role": "user", "content": "updated"}]
        bm.active_messages = new_msgs
        assert bm._branches["main"].messages == new_msgs

    def test_setter_works_on_non_main(self) -> None:
        bm = BranchManager()
        bm.fork("feature")
        bm.switch("feature")
        feature_msgs: list[dict[str, object]] = [{"role": "user", "content": "feature msg"}]
        bm.active_messages = feature_msgs
        assert bm._branches["feature"].messages == feature_msgs
        # Main should be unchanged
        assert bm._branches["main"].messages == []


class TestBranchManagerList:
    """Verify list_branches."""

    def test_lists_all_branches(self) -> None:
        bm = BranchManager()
        bm.fork("feature")
        branches = bm.list_branches()
        assert len(branches) == 2

    def test_active_flag(self) -> None:
        bm = BranchManager()
        bm.fork("feature")
        bm.switch("feature")
        branches = bm.list_branches()
        main_entry = next(b for b in branches if b["name"] == "main")
        feature_entry = next(b for b in branches if b["name"] == "feature")
        assert main_entry["active"] is False
        assert feature_entry["active"] is True

    def test_includes_metadata(self) -> None:
        bm = BranchManager()
        branches = bm.list_branches()
        main_entry = branches[0]
        assert "name" in main_entry
        assert "parent" in main_entry
        assert "messages" in main_entry
        assert "age" in main_entry
        assert "description" in main_entry
        assert "active" in main_entry


class TestBranchManagerGet:
    """Verify get_branch."""

    def test_get_existing(self) -> None:
        bm = BranchManager()
        branch = bm.get_branch("main")
        assert branch is not None
        assert branch.name == "main"

    def test_get_nonexistent(self) -> None:
        bm = BranchManager()
        branch = bm.get_branch("nonexistent")
        assert branch is None


class TestBranchManagerUpdate:
    """Verify update_messages."""

    def test_update_messages(self) -> None:
        bm = BranchManager()
        new_msgs: list[dict[str, object]] = [{"role": "user", "content": "updated"}]
        bm.update_messages(new_msgs)
        assert bm.active_messages == new_msgs


class TestBranchManagerSerialization:
    """Verify to_dict/from_dict roundtrip."""

    def test_to_dict_includes_all_data(self) -> None:
        init_msgs: list[dict[str, object]] = [{"role": "user", "content": "hi"}]
        bm = BranchManager(initial_messages=init_msgs)
        bm.fork("feature", "My feature")
        data = bm.to_dict()
        assert data["active_branch"] == "main"
        assert "main" in data["branches"]
        assert "feature" in data["branches"]
        assert data["branches"]["feature"]["description"] == "My feature"

    def test_roundtrip_preserves_data(self) -> None:
        init_msgs: list[dict[str, object]] = [{"role": "user", "content": "hello"}]
        bm = BranchManager(initial_messages=init_msgs)
        bm.fork("feature")
        bm.switch("feature")
        feature_msgs: list[dict[str, object]] = [{"role": "user", "content": "on feature"}]
        bm.active_messages = feature_msgs

        data = bm.to_dict()
        restored = BranchManager.from_dict(data)

        assert restored.active_branch == "feature"
        assert restored.get_branch("main") is not None
        assert restored.get_branch("feature") is not None
        assert restored.active_messages == feature_msgs

    def test_from_dict_empty_data_defaults(self) -> None:
        restored = BranchManager.from_dict({})
        assert restored.active_branch == "main"

    def test_from_dict_missing_branches(self) -> None:
        restored = BranchManager.from_dict({"active_branch": "other"})
        assert restored.active_branch == "other"
        assert len(restored._branches) == 0

    def test_roundtrip_maintains_message_count(self) -> None:
        msgs: list[dict[str, object]] = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        bm = BranchManager(initial_messages=msgs)
        data = bm.to_dict()
        restored = BranchManager.from_dict(data)
        assert restored.get_branch("main") is not None
        assert restored.get_branch("main").message_count == 2  # type: ignore[union-attr]
