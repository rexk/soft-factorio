# Metrics over time

Key: `metrics`

A way to see how well the factory is working, from rough numbers compared
over time, with people and agents saying what they mean.

## State

| Step | State |
|---|---|
| Research: what similar tools measure | Done: [research.md](research.md) |
| Product brief | Approved 2026-11-06: [product.html](product.html) |
| Design brief | A2 picked 2026-11-06: [design.html](design.html). One ledger per repository, in three stages |
| Stage 1: factory eval ledger, compare, readings | Built, in review: `evals/ledger.jsonl`, `tools/metrics.py`, `tests/test_metrics.py` |
| Stage 2: numbers in adopting repositories | Not started |
| Stage 3: optional quick answer at the retro's end-of-task step | Not started |

## Decided in the interview (2026-11-06)

- **Goal (maintainer's words):** "to be able to have a way to see how well
  our factory is working", starting with numbers that may be ambiguous,
  without being very methodical, and with "each author or systems to
  provide meaning of those or have them to analyze those numbers
  themselves".
- **Scope:** the factory's own evals and repositories that adopted it; the
  factory's evals first.
- **Compare against:** earlier versions only (not factory vs bare, not
  across repositories).
- **Who interprets:** the maintainer, agents, and authors of each adopting
  repository.
- **Perception:** an optional quick answer kept beside the numbers.
- **Must not (added after the first draft):** the numbers are not dogmatic.
  No single number, and especially not lines of code written by agents, is
  the measure of how well the agents or skills are doing. Numbers are read
  in combination, with the reasoning left to the reader (`metrics-X1`
  to `metrics-X4`). The verdict-free line moved from B7 to `metrics-X2`, and
  B8 to B10 became B7 to B9.

## Revised after review (2026-11-06)

The maintainer approved six fixes to the approved product brief:

1. `metrics-X2` and `metrics-X4` cover only what the metrics add: scenario
   pass marks still show, and the evals keep gating as before.
2. `metrics-B9` and V5: nothing leaves a repository unless its authors
   choose to share, with the same consent as upstream lessons.
3. `metrics-B2` and `metrics-B5` count the time before the factory as its
   own period, the baseline for an adopting repository.
4. `metrics-X3`: no number is the headline, and the rest are one step away
   (a view may focus on a few).
5. Each X line names the value point or behaviour it guards.
6. Status and takeaway brought up to date.

The design brief got matching edits: T2, T10–T12, a new `metrics-N6`
(sharing not built yet), and the stage 2 text.

## Agent's calls, for the maintainer to check

- A factory change can be measured before it lands (`metrics-B1`, `metrics-B5`):
  otherwise a change to a skill could only be checked after it shipped.
- Readings are added, never replaced (`metrics-B7`): disagreement between
  readings is worth keeping.
- Numbers never rank people, agents or repositories against each other
  (`metrics-X5`): extends "compare only against earlier versions".

## Decided

- `metrics-Q1` (2026-11-06): A2, the staged ledger.
- `metrics-Q2` (2026-11-06): the quick answer is asked at the retro skill's
  end-of-task step.

## Next

1. Stage 1: the factory's eval ledger, compare and readings (one PR).
2. Stage 2: numbers in adopting repositories (one PR).
3. Stage 3: the optional quick answer (one PR, checked first).
