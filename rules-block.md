<!-- soft-factorio:begin -->
## Software factory

How agents work in this repository. Skills are in `.agents/skills/`
(copied to `.claude/skills/`); guides are in `.agents/factory/guides/`.
Local rules above and below this block win over it.

- **Check intent before building.** When an ask is vague or would change what
  gets built, use `outcome-brief`: agree a product brief (value and behaviour)
  before touching code. Answers to your questions, or "you decide", aren't
  approval; a yes to the brief is. Small, clear asks: say the outcome in two
  lines, then work.
- **Prompt for outcomes.** When you hand work to another agent, state the
  value and the finish line, not the steps (`guides/prompting-for-outcomes.md`).
- **Report in pages.** Results, reviews and questions with structure go in an
  HTML page (`html-for-humans`), not a long chat reply.
- **Ship for review.** Finished, committed work goes out as one pull request
  (`create-pr`).
- **Test behaviour.** Tests prove what the code does for its users, fail when
  that breaks and survive a refactor. Never assert that a field exists or a
  function was called (`behaviour-tests`).
- **Learn.** After a task, or after the person corrects you, run `retro` and
  propose the fix as a reviewable change.
- **Keep rules lean.** This file holds what an agent can't infer from the
  repository (`guides/rules-files.md`).

### Factory settings

| Key | Value |
|---|---|
| `projects` | `docs/projects/` |
| `upstream` | `no` |
| `pr_without_asking` | `yes` |
<!-- soft-factorio:end -->
