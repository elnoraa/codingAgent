# Coding Agent Instructions

These are MANDATORY rules. The coding agent MUST follow all instructions in this file.

## Workflow Rules

1. After implementing each feature or making significant changes, you MUST:
   a. Commit the changes using `git_commit(all=True)`
   b. Push the changes to the remote using `git_push(branch=<current-branch>)`
   c. Verify the commit was successful

2. Always run tests after implementing changes if tests exist.

3. Never modify files outside the project directory.

## Resilience & Stability Rules

1. If a tool call fails, first determine if the error is transient (network, timeout, rate limit).
   If so, retry with adjusted parameters.
2. For file write errors, check if the directory exists before retrying.
3. After completing file modifications, always verify the result using read_file or diff.
4. Run tests after making changes to confirm nothing is broken.
5. If you encounter an unexpected error, report it clearly and suggest a next step.
6. Break complex tasks into numbered sub-steps and complete them sequentially.
