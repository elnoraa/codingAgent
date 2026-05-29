# Coding Agent Instructions

These are MANDATORY rules. The coding agent MUST follow all instructions in this file.

## Workflow Rules

1. After implementing each feature or making significant changes, you MUST:
   a. Commit the changes using `git_commit(all=True)`
   b. Push the changes to the remote using `git_push(branch=<current-branch>)`
   c. Verify the commit was successful

2. Always run tests after implementing changes if tests exist.

3. Never modify files outside the project directory.

4. After successfully implementing a plan from `plans/pending/`, you MUST:
   a. Move the plan to `plans/completed/` by calling the `complete_plan` tool
      with the plan's name. This will also automatically restart the session
      for the next task.

5. When starting a new task, check `plans/pending/` first — if a plan exists
   there that matches the task, implement it and then move it to `plans/completed/`.

6. Before calling `restart_session` to reset the session, you MUST first call
   `complete_plan` to move any pending plan to `plans/completed/`. Always call
   `complete_plan` before `restart_session`, never after.

## Resilience & Stability Rules

1. If a tool call fails, first determine if the error is transient (network, timeout, rate limit).
   If so, retry with adjusted parameters.
2. For file write errors, check if the directory exists before retrying.
3. After completing file modifications, always verify the result using read_file or diff.
4. Run tests after making changes to confirm nothing is broken.
5. If you encounter an unexpected error, report it clearly and suggest a next step.
6. Break complex tasks into numbered sub-steps and complete them sequentially.

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

6. Run the full test suite after every change with `pytest` and confirm
   all tests pass before committing.

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

7. Do NOT create aggregate "roadmap" or "catalog" plans that list multiple features.
   Each feature must have its own individual plan file. For example, if asked to plan
   five features, create five separate plans — one per feature.

Examples:
- `33-feat-add-syntax-highlighting.md`
- `34-fix-crash-on-empty-input.md`
- `35-refactor-extract-command-parser.md`
- `36-docs-update-readme.md`

This convention keeps plan files sortable by number, immediately scannable by type, and consistent across all sessions.
