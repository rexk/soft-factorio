# Changelog

Newest first. The factory has no release tags: a repository records the
commit it installed, and an update lists the factory's commits since then.
This file is the short, human summary.

## 2026-11-06

- Eval ledger (`evals/ledger.jsonl`): every eval pass and `--calibrate`
  appends its numbers with the factory version they measured, including
  turns and skills used per run. Starts with the v1 build's passes of
  2026-11-05, their notes kept as readings.
- `tools/metrics.py`: `compare` puts versions side by side as JSON, or as a
  page with `--html`; `add-reading` records what someone thinks the numbers
  mean. No scores, verdicts or gates.

## 2026-11-04

- `START.md`: the steps an agent follows to apply or update the factory.
- `tools/factory.py`: installs the skills and the `AGENTS.md` block, records
  them in `.agents/factory/manifest.json`, keeps local edits on update and
  stops on conflicts.
- Seed skills: `outcome-brief`, `html-for-humans`, `create-pr`.
- Rules block for a repository's `AGENTS.md`, with a settings table.
- Scenario eval runner (`evals/`): snapshots of local or pinned repositories,
  multi-turn runs with a scripted person, judges calibrated on samples
  (`--calibrate`), and the first scenario, T1.
- `outcome-brief`: "you decide" hands over the decisions, not the approval;
  the agent writes the brief and stops until the person approves it.
- Privacy scan and one check command (`python3 tools/check.py`), run in CI on every push.
