---
name: done-heres-a-summary-of-everything-that-was-impl
status: completed
completed_at: 2026-05-28T17:25:09.530159
created_at: 2026-05-28T17:20:31.329256
---

Done! Here's a summary of everything that was implemented:

---

## Summary

### What was created/modified

**1. `coding-agent.md`** (new file)
- Contains **mandatory rules** the agent must follow
- Currently has 3 workflow rules:
  1. After each feature: `git_commit(all=True)` → `git_push(branch=<current-branch>)` → verify
  2. Always run tests after changes
  3. Never modify files outside the project directory

**2. `repl.py`** (modified)
- `_get_system_prompt()` now reads `coding-agent.md` from the working directory
- If the file exists, its contents are injected as a **"CODING AGENT RULES (MANDATORY)"** section into every system prompt
- The header explicitly says "The following rules are MANDATORY and MUST be followed at all times"
- If the file doesn't exist, nothing changes (backward compatible)

**3. `main.py`** (modified)
- Added a line to the default system prompt telling the agent: *"If a coding-agent.md file exists in the project root, read it first — it contains MANDATORY rules you must follow."*

### How enforcement works

The enforcement is **constitutional** — the rules are baked into the LLM's system prompt on every single turn:
1. `main.py`'s system prompt tells the agent to look for `coding-agent.md`
2. `repl.py`'s `_get_system_prompt()` reads the file at runtime and appends its content as a mandatory section
3. The LLM sees these instructions **every time** it processes a message
4. You can edit `coding-agent.md` anytime — changes take effect on the next turn
5. ✅ All 46 tests pass. Commit pushed to GitHub.
