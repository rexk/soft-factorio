# Harness settings: let the everyday work run without a prompt

The factory's rules tell agents to carry approved work to its finish line:
commit, push a branch, open the pull request and run the repository's checks.
Your harness decides whether each of those stops to ask you. This guide is
for the person: what to allow, what to keep asking about, and where each
harness keeps the setting. An agent points you here; it never changes these
settings itself.

## What to allow, what to keep asking about

| Allow without a prompt | Keep a prompt |
|---|---|
| The everyday git commands: status, diff, log, add, commit, branch, checkout, switch, stash, rebase, merge, fetch, pull, push | Programs nobody has looked at: installing packages (their install scripts run), `npx`, `uvx` or `pnpm dlx` of a package, `curl … \| sh`, scripts the agent just downloaded or wrote |
| `gh pr create`, `gh pr edit`, `gh pr view`, `gh pr checks` | General runners that run anything they're given: `bash -c`, `python3 -c`, `uv run *`, `pnpm exec *` |
| The repository's own check commands, each by name (`pnpm test`, `uv run pytest`) | Deleting files outside the repository, and sending anything to another repository (the factory asks you itself) |

**Allow commands by name.** `Bash(pnpm test *)` lets the agent run the
repository's tests. `Bash(pnpm *)` also lets it fetch and run any package.
The test is whether you've read what the command runs.

**Protect branches in the repository, not on your machine.** Force-push is
part of everyday work (rebasing a branch, squashing before review), so don't
block it locally. On GitHub, a branch protection rule or ruleset on the
default branch blocks force-pushes and deletion, and requires a pull request.
That holds whatever the agent types, and whichever harness it runs in. A
local command rule matches only the command's text, and both harnesses say
it isn't a security boundary.

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
      "Bash(git status *)", "Bash(git diff *)", "Bash(git log *)",
      "Bash(git add *)", "Bash(git commit *)", "Bash(git branch *)",
      "Bash(git checkout *)", "Bash(git switch *)", "Bash(git stash *)",
      "Bash(git rebase *)", "Bash(git merge *)", "Bash(git fetch *)",
      "Bash(git pull *)", "Bash(git push *)",
      "Bash(gh pr create *)", "Bash(gh pr edit *)", "Bash(gh pr view *)",
      "Bash(gh pr checks *)",
      "Bash(pnpm test *)", "Bash(pnpm lint *)", "Bash(uv run pytest *)"
    ]
  }
}
```

- Swap the last line for your repository's own check commands.
- Git subcommands are listed one by one rather than as `Bash(git *)`.
  Options like `git -c` can make git run another program.
- A compound command (`a && b`) runs without a prompt only when every part is
  allowed. A `cd` inside the working folder doesn't count against it.
- Answering a prompt with "Yes, and don't ask again" saves the rule to
  `.claude/settings.local.json`. Check the rule it saves names the command,
  not a whole runner.

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
prompt. A rule matches the command's leading words, so name each command.

```python
# ~/.codex/rules/factory.rules
prefix_rule(pattern = ["git", ["status", "diff", "log", "add", "commit", "branch",
                              "checkout", "switch", "stash", "rebase", "merge",
                              "fetch", "pull", "push"]],
            decision = "allow")
prefix_rule(pattern = ["gh", "pr", ["create", "edit", "view", "checks"]],
            decision = "allow")
prefix_rule(pattern = ["pnpm", "test"], decision = "allow")
```

- Swap the last rule for your repository's own check commands. Don't allow
  a bare runner such as `["npx"]` or `["uv", "run"]`.
- Restart Codex after editing a rules file.
- Check a rule before relying on it, for example
  `codex execpolicy check --rules ~/.codex/rules/factory.rules git push origin my-branch`.
  That one prints `allow`.
- Codex marks rules as experimental. The factory checked these with
  `codex-cli` 0.166.

## Cursor and other harnesses

The factory hasn't checked these yet. Look for the harness's allow-list for
terminal commands (often called auto-run). Allow the same commands as in the
table above, each by name, and protect branches in the repository.
