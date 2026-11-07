# Agent guidelines

This repository is the factory other repositories copy from. Everything in it
is public and lands in other people's repositories.

## Nothing private

- No personal notes, employer or product names, contact details or
  home-directory paths, in any file or commit message.
- Run `python3 tools/check.py` before every commit; it includes the privacy
  scan. Private terms to scan for go in `.privacy-terms` (one per line,
  gitignored), never in a committed file. CI has no copy of them, so this
  local run is the only check for private names.
- Seeds from elsewhere are rewritten, not copied, and the maintainer reviews
  each rewrite before it lands.

## Evals are the referee

- Scenarios and judges (`evals/scenarios/`) define what passing means. Don't
  edit them to make a failing run pass; propose the change and let the
  maintainer decide. The same goes for the behaviour lines they test.
- If a behaviour can't be met, say so. Don't weaken a test to get green.
- Eval runs cost API usage: run the smoke set (T1, T3, T10) when `START.md`
  changes, everything before a release. Test repositories are snapshots in a
  scratch folder and are never pushed to.
- Eval agents may run what a person would approve: everyday git and the
  test repositories' check commands, each by name (`SHIP_TOOLS` in
  `evals/lib.py`). Never general runners or installs, which run programs
  nobody has inspected. A run that stops on a denied command measures the
  harness: fix the list, don't count the run.
- A run cut short by a usage limit is void, not failed; rerun it. Run a full
  pass in batches, the scenario most likely to fail first.
- Each pass appends its numbers to `evals/ledger.jsonl`; commit it with the
  change it measured. `python3 tools/metrics.py compare` puts versions side
  by side. The numbers carry no verdict: add what you think they mean with
  `tools/metrics.py add-reading`.

## Writing skills and tools

- Skills are copied into other repositories, so a skill refers only to its own
  folder, the factory's installed guides (`.agents/factory/guides/`) and the
  host repository's `AGENTS.md` settings.
- Tools and evals are Python 3, standard library only.
- Project plans go in `docs/projects/YYYY-MM-DD-<slug>/`.

## Pull requests

Don't ask for approval for simple operations like git push or creating a PR,
or to advance to the next stage: keep going to the final stage. Check with the
maintainer only before going public or changing a behaviour line, scenario or
judge.

| Key | Value |
|---|---|
| `checks` | `python3 tools/check.py` |
