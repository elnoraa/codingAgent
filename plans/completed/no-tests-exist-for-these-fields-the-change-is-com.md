---
name: no-tests-exist-for-these-fields-the-change-is-com
status: completed
completed_at: 2026-05-28T17:25:55.807645
created_at: 2026-05-28T17:25:47.487586
---

No tests exist for these fields. The change is complete.

---

**Summary of the fix (2 lines added, ~4 lines restructured):**

**Line 320** (approval block) — added: `self._plan_auto_saved = True`
- After the user says "proceed," this flag is set so that the upcoming assistant summary response won't be auto-saved as a new pending plan.

**Lines 399-423** (auto-save block) — wrapped in `if/else`:
- If `_plan_auto_saved` is True: just clear it and skip auto-save
- If `_plan_auto_saved` is False: proceed with the normal auto-save logic (save plan, show approval prompt)

The cycle works as:
1. User describes task → plan auto-saved → `_first_code_turn_done=True`, `_plan_pending_approval=True`
2. User says "proceed" → `_plan_auto_saved=True`, flags cleared
3. Assistant executes tools and shows summary → auto-save block sees `_plan_auto_saved=True`, skips auto-save, resets flag
4. Next user request → `_first_code_turn_done=False`, so plan-first enforcement kicks in again normally
