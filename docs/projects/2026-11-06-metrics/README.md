# Metrics over time

Key: `metrics`

A way to see how well the factory is working, from rough numbers compared
over time, with people and agents saying what they mean.

## State

| Step | State |
|---|---|
| Research: what similar tools measure | Done: [research.md](research.md) |
| Product brief | Written, awaiting the maintainer's approval: [product.html](product.html) |
| Design brief | Not started; waits for the product brief's approval |

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

## Agent's calls, for the maintainer to check

- A factory change can be measured before it lands (`metrics-B1`, `metrics-B5`):
  otherwise a change to a skill could only be checked after it shipped.
- Readings are added, never replaced (`metrics-B7`): disagreement between
  readings is worth keeping.
- Numbers never rank people, agents or repositories against each other
  (`metrics-X5`): extends "compare only against earlier versions".

## Carried to the design brief

- Which numbers to start with: research.md proposes a starting set.
- Where numbers and readings are kept, and in what form.
- Where people see the comparison, and how the quick answer is asked.
- How noisy numbers (few runs) are shown next to each other.

## Next

1. Maintainer approves or corrects the product brief.
2. Design brief: approaches for recording, comparing and reading, factory
   evals first.
