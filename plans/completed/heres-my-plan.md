---
name: heres-my-plan
status: completed
completed_at: 2026-05-28T17:19:00.854490
created_at: 2026-05-28T17:16:41.813681
---

Here's my plan:

---

## Plan: Enforce Commit + Sync After Every Feature

### Understanding

The project already has:
- A `git_commit` tool (stages + commits)
- Pre-commit hooks (linting, type checking, tests)
- Plan-first enforcement (read-only before approval)

Missing:
- No `git push` tool to sync changes to remote
- No `git status` tool for the agent to check repository state
- No enforcement mechanism in system prompts to require commit+push after feature implementation

### Changes

**1. New file: `tools/git_push.py`**
- A `git_push` tool that runs `git push` with optional branch specification
- Reports success/failure, remote URL, and any merge conflicts

**2. New file: `tools/git_status.py`** (read-only)
- A `git_status` tool that shows `git status --short` output
- Also shows current branch and whether there are unpushed commits (`git status -sb` / `git log --oneline @{u}..`)

**3. Modify `repl.py`** — Register both new tools

**4. Modify `main.py`** — Add enforcement instruction to the `DEFAULT_SYSTEM_PROMPT`:
- After completing a feature/implementation step, the agent MUST:
  1. Run `git_status` to check dirty files
  2. Use `git_commit` with `all=true` to commit changes
  3. Use `git_push` to sync to remote

**5. Modify `repl.py`** — Add the same enforcement to the system prompt builder (`_get_system_prompt`)

### Files to modify
| File | Action |
|---|---|
| `tools/git_push.py` | **Create** |
| `tools/git_status.py` | **Create** |
| `repl.py` | **Modify** (register tools, update system prompt) |
| `main.py` | **Modify** (update DEFAULT_SYSTEM_PROMPT) |

### What do you think? Shall I proceed with this plan?
