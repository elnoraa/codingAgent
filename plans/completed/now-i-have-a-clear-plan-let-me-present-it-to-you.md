---
name: now-i-have-a-clear-plan-let-me-present-it-to-you
status: completed
completed_at: 2026-05-28T17:29:16.190991
created_at: 2026-05-28T17:28:35.849816
---

Now I have a clear plan. Let me present it to you.

---

## Plan

The bug: after approval and execution, when a user gives a new task, the new plan's response gets double-auto-saved.

**Root cause:** In the approval handler (line 319), `_first_code_turn_done` is set to `False` "to allow a fresh start." But this:
1. Makes the approval execution turn read-only (can't write files)
2. Causes the approval execution turn's post-block to skip setting flags (since `_plan_auto_saved=True` catches it), leaving both `_first_code_turn_done=False` and `_plan_pending_approval=False`
3. On the next turn, the LLM runs read-only again (because `_first_code_turn_done=False`) and outputs a new plan — which then gets auto-saved

**Fix:** Two changes needed:

1. **Line 319**: Remove `self._first_code_turn_done = False`. Keep it `True` so the execution turn is write-enabled.

2. **Lines 398-423**: Restructure the post-turn block to handle the `_plan_auto_saved` reset independently, allowing it to reset `_first_code_turn_done = False` for the next task.

The new post-turn logic:
```python
# ── Post-turn plan enforcement (code mode) ──────────────────────
if self.mode == "code" and self._plan_auto_saved:
    # Just finished an approved execution turn — reset for plan-first
    self._plan_auto_saved = False
    self._first_code_turn_done = False
elif self.mode == "code" and not self._first_code_turn_done and not self._plan_pending_approval:
    # Normal first turn — set up plan-first enforcement
    self._first_code_turn_done = True
    self._plan_pending_approval = True
    # ... auto-save plan, show approval prompt
```

**Full cycle with fix:**
1. User gives task → read-only LLM plans → plan auto-saved, approval prompt shown
2. User says "proceed" → approval handler: `_plan_pending_approval=False`, `_plan_auto_saved=True` (keeps `_first_code_turn_done=True`) → write-enabled LLM executes → post-turn: `_plan_auto_saved=True` branch resets `_first_code_turn_done=False`
3. User gives new task → read-only LLM plans → cycle starts over correctly

Shall I implement this?
