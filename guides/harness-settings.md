# Harness settings: let the factory's work run without a prompt each time

The factory's rules tell agents to carry approved work to its finish line:
commit, push a branch, open the pull request and run the repository's checks.
Your harness decides whether each of those stops to ask you. This guide is
for the person: what to allow, what to keep guarded, and where each harness
keeps the setting. An agent points you here; it never changes these settings
itself.

## What to allow, what to keep guarded

| Allow without a prompt | Keep a prompt, or block |
|---|---|
| `git add`, `git commit`, `git checkout -b` / `git switch -c` | Force-push (`--force`, `-f`, `+branch`) |
| `git push` of the agent's own branch | Pushing to the default branch |
| `gh pr create`, `gh pr edit`, `gh pr view` | Deleting branches, `rm -rf`, anything outside the repository |
| The repository's test, lint and build commands | Sending anything to another repository (the factory asks you itself) |

**Guard the default branch on the server.** Protect it on GitHub (require a
pull request). Neither harness treats its command rules as a security
boundary: a rule matches the command's text, and a reordered command can slip
past it. Branch protection holds whatever the agent types.

## Claude Code

Settings live in three files, and their permission lists are combined:

| File | Who it affects |
|---|---|
| `~/.claude/settings.json` | you, in every project |
| `.claude/settings.json` | everyone in this repository (commit it) |
| `.claude/settings.local.json` | you, in this repository only |

Rules are checked in the order **deny, then ask, then allow**, and the first
match wins. So a `git push` rule under `ask` prompts even when `allow` has
one too: take it out of `ask` rather than adding to `allow`.

```json
{
  "permissions": {
    "allow": [
      "Bash(git add *)", "Bash(git commit *)", "Bash(git checkout -b *)",
      "Bash(git switch -c *)", "Bash(git push *)",
      "Bash(gh pr create *)", "Bash(gh pr edit *)", "Bash(gh pr view *)",
      "Bash(pnpm test *)", "Bash(uv run pytest *)"
    ],
    "deny": [
      "Bash(git push --force*)", "Bash(git push * --force*)",
      "Bash(git push -f*)", "Bash(git push * -f*)"
    ]
  }
}
```

- Swap the test commands for your repository's own.
- A compound command (`a && b`) runs without a prompt only when every part is
  allowed. A `cd` inside the working folder doesn't count against it.
- Runners like `npx` aren't looked through: allow `Bash(npx vitest *)`, not
  just `vitest`.
- Answering a prompt with "Yes, and don't ask again" saves the rule to
  `.claude/settings.local.json`.
- The deny rules miss `git push origin +main` and other reorderings. That's
  why the default branch is protected on the server.

## Codex

`~/.codex/config.toml` (or `.codex/config.toml` in a trusted project) sets the
mode:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
```

In `workspace-write`, `.git` and `.agents/` stay read-only and the network is
off. So every commit, push and pull request, and installing the factory
itself, needs either your approval or a rule. Rules go in a `.rules` file in
`~/.codex/rules/` (or `<repo>/.codex/rules/` in a trusted project). A rule
with `decision = "allow"` runs that command outside the sandbox without a
prompt. When several rules match, the strictest decision wins.

```python
# ~/.codex/rules/factory.rules
prefix_rule(pattern = ["git", "push", ["--force", "-f", "--force-with-lease"]],
            decision = "forbidden", justification = "No force-push from agents.")
prefix_rule(pattern = ["git", ["add", "commit", "push"]], decision = "allow")
prefix_rule(pattern = ["git", ["checkout", "switch"]], decision = "allow")
prefix_rule(pattern = ["gh", "pr", ["create", "edit", "view"]], decision = "allow")
```

- Restart Codex after editing a rules file.
- Check a rule before relying on it, for example
  `codex execpolicy check --rules ~/.codex/rules/factory.rules git push --force origin x`.
  That one prints `forbidden`.
- A rule matches the command's leading words only.
  `git push origin --force` and `git push origin +main` aren't caught by the
  forbidden rule above, and the allow rule lets them through. Branch
  protection covers them.
- Codex marks rules as experimental. The factory checked these with
  `codex-cli` 0.166.

## Cursor and other harnesses

The factory hasn't checked these yet. Look for the harness's allow-list for
terminal commands (often called auto-run). Allow the same commands as in the
table above, and keep the same guards.
