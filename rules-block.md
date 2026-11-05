## Software factory

How agents work in this repository. Skills are in `.agents/skills/` (copied
to `.claude/skills/`). The repository's own rules outside this block win
over it.

- **Check intent before building.** When an ask is vague or would change what
  gets built, use `outcome-brief`: agree a product brief (value and behaviour)
  before touching code. Answers to your questions, or "you decide", aren't
  approval; a yes to the brief is. Small, clear asks: say the outcome in two
  lines, then work.
- **Prompt for outcomes.** When you hand work to another agent, state the
  value and the finish line, not the steps.
- **Report in pages.** Results, reviews and questions with structure go in an
  HTML page (`html-for-humans`), not a long chat reply.
- **Ship for review.** Finished, committed work goes out as one pull request
  (`create-pr`).
- **Test behaviour.** Tests prove what the code does for its users, fail when
  that breaks and survive a refactor. Never assert only that a field exists
  or a function was called.
- **Keep rules lean.** This file holds what an agent can't infer from the
  repository.

The block between the `soft-factorio` markers is installed by the factory
and updated by reapplying it. Edits inside it are kept on update and
reported. The settings below belong to this repository.
