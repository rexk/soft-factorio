# soft-factorio

A software factory any repository can adopt: the skills, rules and guidance
for building software with agents. Point a repository's agent at one file and
it applies the factory, fitted to that repository's own conventions. Run it
again later to update; local changes are kept.

> **Status: v1 in progress.** `START.md` and the manifest helper are not
> written yet, so there is nothing to apply. The skills under `skills/` can be
> read and copied by hand in the meantime.

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
| `rules-block.md` | The marked block added to a repository's `AGENTS.md` |
| `evals/` | Scenarios that put an agent in a real repository with a task and judge what it did |
| `tools/` | The check command and the privacy scan |
| `CHANGELOG.md` | What each tagged release changed |

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
