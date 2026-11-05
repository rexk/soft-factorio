"""T7 Finish a task (B8).

typewirets with the factory installed, an origin that looks like GitHub, and
a fake gh that logs pull requests. The person asks for a small, real fix (a
misspelled exported type name) without saying anything about pull requests.

Pass when exactly one pull request was opened (code), and a judge model,
calibrated on evals/calibration/t7/, finds its title and body meet the
factory's writing guide.
"""

from __future__ import annotations

import json
from pathlib import Path

import lib

ID = "T7"
BEHAVIOURS = ["B8"]
REPO = "typewirets"
PASS_RATE = 0.8
TASK = ("The exported type TypeWireContianerOpts in packages/core is misspelled. Fix the "
        "name without breaking anyone who imports the old one.")

RUBRIC = """You judge the title and description of a pull request a coding agent
opened. The repository's guide says:
- Title: says specifically what the change does, so it stands alone in a list
  of titles; imperative mood ("Fix", "Add", not "Fixed"/"Fixes"); at most 72
  characters; no trailing period, no "WIP", no emoji. A conventional-commit
  prefix like "fix(core): " is fine.
- Body: opens with what changed and what it does, then why. Only then, if
  useful: risk, how to migrate, where to look. Leaves out boilerplate headings
  the repository doesn't ask for (Summary/Changes/Test plan), commit lists,
  logs and the story of the session. Claims (tests run, numbers) must be ones
  the body can stand behind; saying tests were not run is fine.
- Footer lines a tool adds (like "Generated with ...") are fine.

Decide:
- title_ok: true or false.
- body_ok: true or false.
- reason: one sentence naming the main problem, if any.

JSON keys: title_ok, body_ok, reason."""


def judge_pr(title: str, body: str) -> dict:
    return lib.model_judge(RUBRIC, f"TITLE:\n{title}\n\nBODY:\n{body}")


def accepts(v: dict) -> bool:
    return v.get("title_ok") is True and v.get("body_ok") is True


def judge_accepts(sample: str) -> bool:
    pr = json.loads(sample)
    return accepts(judge_pr(pr["title"], pr["body"]))


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    repo = lib.snapshot(REPO, dest)
    lib.preinstall_factory(repo)
    lib.commit_all(repo, "Apply software factory (preinstalled by eval)")
    lib.add_local_remote(repo)
    gh_log = logdir / "gh.jsonl"
    agent = lib.run_agent(repo, TASK, logdir / "task.jsonl", model,
                          extra_tools=lib.SHIP_TOOLS, fake_gh_log=gh_log)
    prs = [c for c in lib.gh_calls(gh_log) if c.get("created") == "pr"]
    verdict = judge_pr(prs[0].get("title") or "", prs[0].get("body") or "") if len(prs) == 1 else None
    return {
        "pass": len(prs) == 1 and accepts(verdict or {}),
        "prs_opened": len(prs),
        "titles": [p.get("title") for p in prs],
        "bodies": [p.get("body") for p in prs],
        "judge": verdict,
        "skills_used": agent.skills_used,
        "cost_usd": round(agent.cost_usd, 3),
        "agent_error": agent.is_error,
        "final_reply": agent.result[:1500],
    }
