---
name: both-changes-are-in-place-heres-a-summary-of-wha
status: completed
completed_at: 2026-05-28T17:29:54.237760
created_at: 2026-05-28T17:29:46.962651
---

Both changes are in place. Here's a summary of what was fixed:

**Change 1** (line 318-320) — Approval handler: Removed `self._first_code_turn_done = False`. Now on approval, `_first_code_turn_done` stays `True`, which keeps the execution turn write-enabled.

**Change 2** (lines 398-422) — Post-turn block: Restructured into two clear branches:
- **`if _plan_auto_saved`**: After an approved execution turn finishes, resets `_first_code_turn_done = False` so the next user task will trigger plan-first mode.
- **`elif not _first_code_turn_done and not _plan_pending_approval`**: On a fresh task (no plan yet), sets up plan-first enforcement with auto-save and approval prompt.
