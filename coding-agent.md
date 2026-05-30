# Coding Agent Instructions

These are MANDATORY rules. The coding agent MUST follow all instructions in this file.

## Workflow Rules

0. **STARTUP RITUAL (MANDATORY — run this at the beginning of EVERY task)**: Before touching any code or running any tool that modifies files, execute these checks in order:

   a. **Check for existing plan**: Run `list_directory("plans/pending/")` to see if a plan already exists for this task.
   b. **Check current branch**: Run `git_branch(action="list")` to confirm which branch you're on.
   c. **If no plan exists**: Call `write_plan` to create one in `plans/pending/`. Do NOT skip this step — do not write code without a plan.
   d. **If on main (or not on a task branch)**: Create and switch to a feature branch via `git_branch(action="create", name="<task-branch>")` then `git_branch(action="switch", name="<task-branch>")`.
   e. **Confirm before proceeding**: State clearly in your response: "Check passed — plan exists in plans/pending/, on branch <branch-name>."

   Violating any of (a)–(d) = breaking the rules. The startup ritual is not optional.

1. **Plan-first cycle**: When starting a new task, first check `plans/pending/` — if a plan exists
   there that matches the task, implement it. If no plan exists, create a new plan using `write_plan`
   and save it to `plans/pending/` following the naming convention below.

2. **Branch-per-task**: For each task, create a separate git branch from `main`:
   a. Run `git_branch(action="create", name="<task-branch>")` to create a new branch
   b. Run `git_branch(action="switch", name="<task-branch>")` to switch to it
   c. Use a descriptive name like `feat-<short-description>` or `fix-<short-description>`

3. **Implement and commit**: After implementing the plan on the task branch:
   a. Commit the changes using `git_commit(all=True)`
   b. Push the branch to the remote using `git_push(branch=<task-branch>)`

4. **Merge back to main**: After the feature branch is pushed:
   a. Switch to main: `git_branch(action="switch", name="main")`
   b. Merge the feature branch: `git_branch(action="merge", name="<task-branch>", source="<task-branch>")`
   c. Push main: `git_push(branch="main")`
   d. Delete the feature branch: `git_branch(action="delete", name="<task-branch>")`

5. **No manual test running**: The pre-commit hook automatically runs tests on commit.
   Do NOT call `run_tests` manually — the hook handles this.

6. **Documentation and tests**: Plans and code changes MUST both account for documentation and testing:
   a. Every plan saved to `plans/pending/` MUST include dedicated sections for:
      - **Documentation**: What docs will be updated (README.md, docstrings, etc.)
      - **Testing**: What tests will be added or modified
   b. When making code changes during implementation, you MUST:
      - Update the `README.md` if the change affects user-facing features, commands, or project structure
      - Add or update docstrings on all new or modified functions, classes, and methods
      - Create new test files (or add to existing ones) for all new functionality
   c. All tests MUST use isolated temp directories (via `tempfile.TemporaryDirectory`
      or pytest `tmp_path` fixture) — never write to the real project directories

7. After successfully implementing a plan from `plans/pending/`, you MUST:
   a. Move the plan to `plans/completed/` by calling the `complete_plan` tool
      with the plan's name. This will also automatically restart the session
      for the next task.

8. Before calling `restart_session` to reset the session, you MUST first call
   `complete_plan` to move any pending plan to `plans/completed/`. Always call
   `complete_plan` before `restart_session`, never after.

9. Never modify files outside the project directory.

## Resilience & Stability Rules

1. If a tool call fails, first determine if the error is transient (network, timeout, rate limit).
   If so, retry with adjusted parameters.
2. For file write errors, check if the directory exists before retrying.
3. After completing file modifications, always verify the result using read_file or diff.
4. If you encounter an unexpected error, report it clearly and suggest a next step.
5. Break complex tasks into numbered sub-steps and complete them sequentially.

## File Operations Rules

1. When moving or renaming files, do NOT use `write_file` (reading content and writing to a new path).
   Instead, use `bash` with `mv`, `rename`, or `git mv` to move/rename files.
   Using `write_file` for moves is inefficient, loses file metadata, and leaves the original file behind.

## Testing Rules

1. Every fix MUST include new tests that would catch the bug if it recurred.
   Do not rely solely on existing tests — add tests specific to the fix.

2. Test the exposed/public API, not just internal helper functions. For tools,
   call the `execute()` function directly with a `ToolContext`. If the bug
   involves path resolution, use a temp directory fixture in the test.

3. Always test edge cases:
   - Empty strings, whitespace-only values, missing required arguments
   - Relative vs absolute paths, unusual working directory values
   - Boundary conditions (empty input, maximum input length if applicable)

4. After every file-write operation in a test, assert the file actually
   exists using `os.path.isfile()` or `Path.is_file()`. This catches
   silent path resolution failures.

5. All tests MUST use isolated temp directories (via `tempfile.TemporaryDirectory`
   or pytest `tmp_path` fixture) — never write to the real project directories
   like `plans/` or `sessions/` during tests.

## Multi-Agent & Swarm Rules

1. When spawning sub-agents, provide clear, self-contained tasks that can be completed independently.
2. Check agent results with `list_agents` before proceeding with dependent work.
3. Always terminate completed sub-agents with `terminate_agent` to free resources.
4. For swarms, prefer the `run_swarm` tool which handles lifecycle automatically.
5. Sub-agents have a maximum nesting depth of 3 — do not attempt to spawn agents from workers.
6. When using `send_to_agent`, use `message_type="instruction"` for delegating work and `message_type="result"` for returning data.

## Plan Naming Convention

When saving plans to `plans/pending/`, use the following naming format:

```
<number>-<type>-<ShortDescription>.md
```

Where `<type>` is one of: `feat`, `fix`, `refactor`, `docs`, `perf`, `ci`, `chore`, `security`, `deps`, `test`, `spike`.

Do NOT create aggregate "roadmap" or "catalog" plans that list multiple features.
Each feature must have its own individual plan file. For example, if asked to plan
five features, create five separate plans — one per feature.

Examples:
- `33-feat-add-syntax-highlighting.md`
- `34-fix-crash-on-empty-input.md`
- `35-refactor-extract-command-parser.md`
- `36-docs-update-readme.md`

This convention keeps plan files sortable by number, immediately scannable by type, and consistent across all sessions.
