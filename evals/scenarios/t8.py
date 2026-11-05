"""T8 Add a rule (B9).

typewirets with the factory installed. The person says "Always run `pnpm
lint` before committing." (the design brief's "make lint", in this
repository's own command).

Pass when the only change is to the rules file, outside the factory's
marked block: one short added line and nothing removed (code), and a judge
model, calibrated on evals/calibration/t8/, finds the added text is the rule
and nothing an agent could infer from the repository.
"""

from __future__ import annotations

from pathlib import Path

import lib

ID = "T8"
BEHAVIOURS = ["B9"]
REPO = "typewirets"
PASS_RATE = 0.8
TASK = "Always run `pnpm lint` before committing."
RULES_FILES = {"AGENTS.md", "CLAUDE.md"}

RUBRIC = """A person told a coding agent: "Always run `pnpm lint` before committing."
The agent edited the repository's rules file (AGENTS.md), which every agent
reads at the start of every session, so it should hold only what an agent
can't infer from the repository. Below is the text the agent added.

Decide:
- states_rule: true if the added text tells agents to run `pnpm lint` before
  committing.
- only_the_rule: true if it adds nothing else: no explanation of what the
  command does or which tool it runs, no headings, no restated facts from
  package.json or the README, no other rules.
- reason: one sentence.

JSON keys: states_rule, only_the_rule, reason."""


def judge_added(text: str) -> dict:
    return lib.model_judge(RUBRIC, text)


def accepts(v: dict) -> bool:
    return v.get("states_rule") is True and v.get("only_the_rule") is True


def judge_accepts(sample: str) -> bool:
    return accepts(judge_added(sample))


def added_and_removed(diff: str) -> tuple[list[str], list[str]]:
    added, removed = [], []
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++") and line[1:].strip():
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---") and line[1:].strip():
            removed.append(line[1:])
    return added, removed


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    repo = lib.snapshot(REPO, dest)
    lib.preinstall_factory(repo)
    base = lib.commit_all(repo, "Apply software factory (preinstalled by eval)")
    block_before = (repo / "AGENTS.md").read_text().split("<!-- soft-factorio:begin -->")[1] \
        .split("<!-- soft-factorio:end -->")[0]
    agent = lib.run_agent(repo, TASK, logdir / "task.jsonl", model)
    ev = lib.collect(repo, base, agent)
    (logdir / "diff.patch").write_text(ev.diff)
    rules = (repo / "AGENTS.md").read_text()
    block_after = rules.split("<!-- soft-factorio:begin -->")[1].split("<!-- soft-factorio:end -->")[0] \
        if "<!-- soft-factorio:begin -->" in rules else ""
    other = [p for p in ev.paths() if p not in RULES_FILES]
    added, removed = added_and_removed(ev.diff)
    short = len(added) == 1 and len(added[0]) <= 120
    verdict = judge_added("\n".join(added)) if added else None
    return {
        "pass": (not other and short and not removed and block_after == block_before
                 and accepts(verdict or {})),
        "files_changed": ev.paths(),
        "added": added,
        "removed": removed,
        "block_untouched": block_after == block_before,
        "judge": verdict,
        "cost_usd": round(agent.cost_usd, 3),
        "agent_error": agent.is_error,
        "final_reply": agent.result[:1200],
    }
