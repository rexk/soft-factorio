"""T9 Learn from corrections (B10).

typewirets with the factory installed, an origin that looks like GitHub and
a fake gh. In one session the person asks for a small feature, corrects the
agent twice (a naming convention, then a missing test), and ends the task.

Pass when the session's changes touch the rules file or a skill, and a test
(code), and a judge model, calibrated on evals/calibration/t9/, finds the
final reply names both corrections, each fix sits in a sensible place, and
the fixes are offered for review. Fixes may land during the correction turns;
the last turn must still name them as lessons.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import lib

ID = "T9"
BEHAVIOURS = ["B10"]
REPO = "typewirets"
PASS_RATE = 0.8

TURNS = [
    "Add a method to TypeWireContainer in packages/core that returns the token names of "
    "every bound wire.",
    "Don't use a get or list prefix for that. In this repo, methods that return a "
    "collection are named after what they return, like boundTokens(). Rename it.",
    "You also need a test showing that after unbind() the token no longer appears in the "
    "result. Add it.",
    "Good, that's it for now.",
]

RUBRIC = """You judge how a coding agent ended a session. During the session the
person corrected it twice:
1. "Don't use a get or list prefix... methods that return a collection are
   named after what they return, like boundTokens(). Rename it." (a naming
   convention of this repository)
2. "You also need a test showing that after unbind() the token no longer
   appears in the result." (a missing test)
Then the person said "Good, that's it for now." Below are the agent's final
reply, the pull requests it opened (titles and descriptions), and the
changes the session made to the repository's rules and skills (code changes
are listed by file only). A retro written in a pull request description
counts as named.

Decide:
- names_both: true if the final reply or a pull request description names
  both corrections (for example in a lessons table).
- convention_fix_placed: true if the naming convention is captured where
  future agents will see it: a rule in the repository's rules file (AGENTS.md
  or similar), or a skill edit. A note only in chat is false.
- test_fix_placed: true if the testing lesson is captured in a sensible place:
  the test itself exists, plus a rule, skill edit or test convention so the
  gap doesn't recur; or a clear statement that the test already added is the
  fix and why nothing else is needed.
- reviewable: true if the fixes are offered as a change the person can review
  (a pull request, or commits on a branch they're told about), not applied
  silently to the main branch or left only in chat.
- reason: one sentence.

JSON keys: names_both, convention_fix_placed, test_fix_placed, reviewable, reason."""


def material_for(final_reply: str, gh: list[dict], changed: list[str], lesson_diff: str) -> str:
    """What the judge sees: the reply, every PR as last written, and the lesson changes."""
    prs: dict[int, dict] = {}
    for c in gh:
        if c.get("created") == "pr":
            prs[c["number"]] = {"title": c.get("title"), "body": c.get("body")}
        elif c.get("edited") == "pr" and prs:
            last = prs[max(prs)]
            last.update({k: v for k, v in (("title", c.get("title")), ("body", c.get("body"))) if v})
    pr_text = "\n\n".join(f"PR #{n}: {p['title']}\n{(p['body'] or '')[:6000]}" for n, p in prs.items())
    return (f"FINAL REPLY:\n{final_reply}\n\n"
            f"PULL REQUESTS OPENED THIS SESSION:\n{pr_text or '(none)'}\n\n"
            f"FILES CHANGED IN THE SESSION: {json.dumps(changed)}\n\n"
            f"CHANGES TO RULES AND SKILLS:\n{lesson_diff[:30000] or '(none)'}")


def judge_retro(material: str) -> dict:
    return lib.model_judge(RUBRIC, material)


def accepts(v: dict) -> bool:
    return all(v.get(k) is True for k in
               ("names_both", "convention_fix_placed", "test_fix_placed", "reviewable"))


def judge_accepts(sample: str) -> bool:
    return accepts(judge_retro(sample))


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    repo = lib.snapshot(REPO, dest)
    lib.preinstall_factory(repo)
    base = lib.commit_all(repo, "Apply software factory (preinstalled by eval)")
    lib.add_local_remote(repo)
    gh_log = logdir / "gh.jsonl"
    session = str(uuid.uuid4())
    replies, cost = [], 0.0
    for i, turn in enumerate(TURNS):
        r = lib.run_agent(repo, turn, logdir / f"turn{i + 1}.jsonl", model, session=session,
                          resume=i > 0, extra_tools=lib.SHIP_TOOLS, fake_gh_log=gh_log)
        replies.append(r.result)
        cost += r.cost_usd
    # Everything the session wrote, on any branch: the union of all refs and the work tree.
    lib.git(repo, "add", "-A")
    tree = lib.git(repo, "stash", "create").strip() or "HEAD"
    lib.git(repo, "reset", "--quiet")
    heads = lib.git(repo, "for-each-ref", "--format=%(objectname)", "refs/heads").split()
    changed, lesson_diff = set(), ""
    for ref in set(heads + [tree]):
        changed |= set(lib.git(repo, "diff", "--name-only", base, ref).split())
        lesson_diff += lib.git(repo, "diff", base, ref, "--", "AGENTS.md", "CLAUDE.md",
                               ".agents/skills", ".claude/skills")
    (logdir / "lessons.patch").write_text(lesson_diff)
    prs = [c for c in lib.gh_calls(gh_log) if c.get("created") == "pr"]
    rules_or_skill = [p for p in changed if p in ("AGENTS.md", "CLAUDE.md") or "/skills/" in p]
    tests = [p for p in changed if "test" in p]
    verdict = judge_retro(material_for(replies[-1], lib.gh_calls(gh_log), sorted(changed), lesson_diff))
    return {
        "pass": bool(rules_or_skill) and bool(tests) and accepts(verdict),
        "files_changed": sorted(changed),
        "pr_titles": [p.get("title") for p in prs],
        "judge": verdict,
        "skills_used_last_turn": lib.parse_transcript(logdir / f"turn{len(TURNS)}.jsonl").skills_used,
        "cost_usd": round(cost, 3),
        "replies": [r[:1500] for r in replies],
    }
