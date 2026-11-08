# Changelog

Newest first. The factory has no release tags: a repository records the
commit it installed, and an update lists the factory's commits since then.
This file is the short, human summary.

Mark an entry **Action needed:** when a repository's person must do something
the helper can't, such as change a harness setting. An update prints the
entries added since the installed version and lists those in its pull
request.

## 2026-11-06

- `outcome-brief`: every product brief now states what the product must
  never do, as observable `X1…` lines next to value and behaviour. Anti-goals
  are asked for the product brief, and the design brief's test plan covers
  each `X` line. Build limits stay in the design brief's `N` bounds.
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
