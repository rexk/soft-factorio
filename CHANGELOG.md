# Changelog

Newest first. The factory has no release tags: a repository records the
commit it installed, and an update lists the factory's commits since then.
This file is the short, human summary.

Mark an entry **Action needed:** when a repository's person must do something
the helper can't, such as change a harness setting. An update prints the
entries added since the installed version and lists those in its pull
request.

## 2026-11-06

- Eval ledger (`evals/ledger.jsonl`): every eval pass and `--calibrate`
  appends its numbers with the factory version they measured, including
  turns and skills used per run. Starts with the v1 build's passes of
  2026-11-05, their notes kept as readings.
- `tools/metrics.py`: `compare` puts versions side by side as JSON, or as a
  page with `--html`; `add-reading` records what someone thinks the numbers
  mean. No scores, verdicts or gates.
- `metrics` skill, installed with the factory: a repository's own numbers
  (agent pull requests merged, closed or open, review rounds, time to
  merge, reverts, corrections from retro Lessons tables) before the
  factory and for each factory version it applied, computed on demand from
  git, the manifest's history and `gh pr list`. Readings go in
  `.agents/metrics/ledger.jsonl`. The ledger code it shares with
  `tools/metrics.py` now lives in the skill's folder.
- `update-factory` skill: "update the factory" (or "is there an update?")
  in a repository reads the installed version from its manifest, shows what
  changed, and updates by following the factory's current `START.md`.
- `factory.py plan` and `apply` say when a repository is up to date, and
  print the changelog entries added since the installed version.
- Lessons sent upstream carry evidence (or say there is none) instead of a
  factory version.
- The harness settings guide explains why the harness keeps asking for
  approval, with fixes.
- `outcome-brief`: the product brief holds value and behaviour only. A call
  the agent makes for the person goes on the line it shapes, marked "my
  call"; a call about how goes to the design brief.

## 2026-11-05

- Harness settings guide (`guides/harness-settings.md`), pointed to from
  every apply's pull request.
- Project slugs are their keys; items are cited like issue keys.

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
