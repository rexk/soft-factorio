---
name: metrics
description: Show this repository's own numbers (how agents' pull requests fared, review rounds, time to merge, reverts, corrections from retro Lessons tables) before the factory and for each factory version it has applied, side by side, and record what people or agents think they mean. Use when someone asks how the factory or the agents are doing here, whether things got better or worse since an update, for numbers, metrics or a before-and-after, or to write down a reading of them. Not a score: never turn the numbers into a verdict, a target or a ranking.
---

# metrics: this repository's numbers, compared over time

**Outcome:** the person sees this repository's numbers for every factory
version it has had, and for the time before its first one, next to each
other with the change between them. Every number says what it counts,
where it came from and how many pull requests or commits it rests on. If
they say what they make of it, their reading is kept with the numbers.

The script is `metrics.py` in this skill's folder (`.agents/skills/metrics/`
once installed). It needs only `python3` and git; pull request numbers also
need the `gh` CLI, signed in. Nothing needs switching on first: every
number is computed now from the repository's history, the history of
`.agents/factory/manifest.json` and its pull requests. Only readings and
quick answers are stored, in `.agents/metrics/ledger.jsonl`.

A quick answer is what the person who asked for a task said about it when
it ended: how much they had to step in, and whether they would take the
pull request as is. The `create-pr` skill asks the first time it reports
the task's pull request, or the `retro` skill at its end-of-task step when a
correction came before that; it is asked once per task. Either records the answer with
`add-answer`. `compare` lists each answer beside
its pull request's own numbers, apart from the numbers by version, which
answers never change.

## Steps

1. **Compute the comparison.** From the repository root:

   ```bash
   python3 .agents/skills/metrics/metrics.py compare --html
   ```

   Name versions to narrow it (`compare before 1a2b3c4`); by default every
   version is shown. It prints the comparison as JSON and writes a page to
   `.scratch/metrics/repository.html`, which git ignores. If the
   repository's agents push branches with a prefix other than the built-in
   ones (see `agent_rule` in the output), add `--agent-branch PREFIX`.
   *Done when* the command exits 0. A number that couldn't be computed
   shows as missing, with the reason as its source; that is a result, not
   a failure.
2. **Hand it over.** Give the person the page, the way your harness allows,
   and two lines in chat: which versions are compared, and several numbers
   that moved, each with its count. Say the counts are small when they are.
   *Done when* the person has the page.
3. **Ask for a reading, once.** Ask what they make of it, if anything. If
   they answer, record it in their words:

   ```bash
   python3 .agents/skills/metrics/metrics.py add-reading \
     --about VERSION [VERSION ...] --author "<their role, e.g. maintainer>" \
     --text "<their words>"
   ```

   If they ask for your reading, add it as a separate one with `--author`
   naming you as an agent. Commit the ledger with the rest of the work.
   *Done when* each reading given is in the ledger, or they gave none.

## Rules

- **No verdict.** Don't call a number or a version good, bad, better or
  worse, and don't sum them into a score. A change is a difference; what
  it means is the reader's to say, in a reading.
- **No headline.** Never report one number alone: show several together,
  with the page one step away.
- **No target or gate.** Don't make a number something to hit, and don't
  fail, block or reward anything because a number moved.
- **No ranking.** Compare a version only with this repository's earlier
  versions. Never compare people, agents or repositories with each other,
  and never report lines of code as a measure of anything.
- **Nothing leaves the repository.** The script only reads git and `gh pr
  list`; don't post the numbers or readings anywhere (issues, comments,
  chat tools, the factory) unless the person asks for that, each time.
- **Readings are added, never edited.** A new reading sits beside the
  earlier ones; don't rewrite or remove the ledger's lines.
- **Answers stay as given.** Show quick answers one by one beside their
  pull requests; don't count, total or score them, and don't record or
  compare who gave them.
