# soft-factorio

A software factory any repository can adopt: the skills, rules and guidance
for building software with agents. Point a repository's agent at one file and
it applies the factory, fitted to that repository's own conventions. Run it
again later to update; local changes are kept.

> **Status: v1 in progress; expect changes.** There are no release tags:
> applying installs the default branch, and the repository records the
> commit it installed.

## Apply it

Tell your repository's agent:

> Apply the software factory from https://github.com/rexk/soft-factorio by
> following its START.md.

It asks you one question (whether this repository sends lessons back), then
opens a pull request with the skills, one marked block in `AGENTS.md`, and a
record of what it installed. Run the same request later to update: local
edits are kept, and the agent asks before overriding any.

## What a repository gets

| Behaviour | What it means for the repository |
|---|---|
| Intent first | On a vague ask, the agent agrees a product brief (value and behaviour) before touching code (`outcome-brief`) |
| Readable reports | Results, reviews and questions arrive as phone-friendly HTML pages (`html-for-humans`) |
| Ship for review | Finished work arrives as one pull request with a clear title and description (`create-pr`) |
| Lean rules | One short marked block in `AGENTS.md`, plus a settings table; the repository's own rules win |
| Any agent tool | Plain `SKILL.md` files, read by Claude Code, Codex and Cursor |

## Layout

| Path | What it holds |
|---|---|
| `skills/` | Skills copied into a repository's `.agents/skills/` (and `.claude/skills/`) |
| `START.md` | The steps an agent follows to apply or update the factory |
| `rules-block.md` | The marked block added to a repository's `AGENTS.md` |
| `factory.json` | Which skills install, and the default settings |
| `evals/` | Scenarios that put an agent in a real repository with a task and judge what it did |
| `tools/` | The apply helper (`factory.py`), the check command and the privacy scan |
| `CHANGELOG.md` | A dated summary of what changed |

## Checks

```bash
python3 tools/check.py
```

Runs the unit tests and the privacy scan. Python 3, standard library only,
locally and in CI. Scenario evals run agent sessions, which cost API usage,
so they run separately:

```bash
python3 evals/run.py T1 --arms preinstalled,bare --runs 3
```

## License

MIT, see [LICENSE](LICENSE).
