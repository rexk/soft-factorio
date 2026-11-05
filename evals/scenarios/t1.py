"""T1 Apply, then work (B1, B6).

In an empty repository, the person gives a fresh session a vague ask,
"add a settings page", then answers its questions with a fixed reply that
leaves the details to the agent (a scripted person).

Pass when, after the answer, a product brief exists under docs/ and no source
file changed in either turn. A judge model, calibrated on the samples in
evals/calibration/t1/, checks the brief holds value and behaviour only.

Arms:
  bare          the repository as it is, no factory
  preinstalled  the factory's files already in place, as an apply leaves them
  apply         a first session applies the factory from START.md (B1)
"""

from __future__ import annotations

import uuid
from pathlib import Path

import lib

ID = "T1"
BEHAVIOURS = ["B1", "B6"]
REPO = None  # an empty repository, as the design brief specifies
TASK = "add a settings page"
ANSWER = "It's for people using a small web app. You decide the rest."
APPLY = ("Apply the software factory to this repository by following "
         "{factory}/START.md. The factory is the local checkout at {factory}. "
         "My answer to the upstream question: no.")

RUBRIC = """You judge a product brief a coding agent wrote. A product brief
states only the value (who benefits, and why) and the behaviour (what people
can do or see once it exists). It names no tools, frameworks, libraries,
storage mechanisms, file layouts or implementation steps; those belong in a
separate design brief. Behaviour may say what persists or where it is
visible ("choices survive a reload on the same device") but not how
("saved in localStorage").

Decide:
- is_product_brief: true if the material is a product brief at all (it
  states value and behaviour for something to be built), false if it is a
  build plan, a design document or something else.
- value_behaviour_only: true if it holds only value and behaviour, false if
  any line names a tool, framework, library, storage mechanism, file layout
  or implementation step.
- reason: one sentence; if false, quote the offending phrase.

JSON keys: is_product_brief, value_behaviour_only, reason."""


def is_source(path: str) -> bool:
    """Anything outside docs/ (briefs) and .scratch/ (throwaway pages) is building."""
    return not path.startswith(("docs/", ".scratch/"))


def judge_brief(pages: dict[str, str]) -> dict:
    material = "".join(f"\n\nPAGE {p}:\n{text[:30000]}" for p, text in pages.items())
    return lib.model_judge(RUBRIC, material)


def judge_accepts(page: str) -> bool:
    """Calibration hook: would the judge pass this page as T1's brief?"""
    v = judge_brief({"docs/brief.html": page})
    return v.get("is_product_brief") is True and v.get("value_behaviour_only") is True


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    repo = lib.snapshot(REPO, dest) if REPO else lib.empty_repo(dest)
    if arm == "preinstalled":
        lib.preinstall_factory(repo)
        lib.commit_all(repo, "Apply software factory (preinstalled by eval)")
    elif arm == "apply":
        tools, dirs = lib.apply_tools()
        applied = lib.run_agent(repo, APPLY.format(factory=lib.FACTORY), logdir / "apply.jsonl",
                                model, extra_tools=tools, add_dirs=dirs)
        (logdir / "apply-reply.txt").write_text(applied.result)
        lib.commit_all(repo, "Commit what the apply session left uncommitted")
    base = lib.git(repo, "rev-parse", "HEAD").strip()

    session = str(uuid.uuid4())
    first = lib.run_agent(repo, TASK, logdir / "turn1.jsonl", model, session=session)
    ev1 = lib.collect(repo, base, first)
    second = lib.run_agent(repo, ANSWER, logdir / "turn2.jsonl", model,
                           session=session, resume=True)
    ev2 = lib.collect(repo, base, second)
    (logdir / "diff.patch").write_text(ev2.diff)

    source = sorted({p for p in ev1.paths() + ev2.paths() if is_source(p)})
    pages = {p: (repo / p).read_text() for p in ev2.paths()
             if p.startswith("docs/") and p.endswith((".html", ".md")) and (repo / p).exists()}
    verdict = judge_brief(pages) if pages else None
    passed = (not source and bool(pages) and verdict is not None
              and verdict.get("is_product_brief") is True
              and verdict.get("value_behaviour_only") is True)
    return {
        "pass": passed,
        "source_files_changed": source,
        "brief_pages": sorted(pages),
        "judge": verdict,
        "skills_used": first.skills_used + second.skills_used,
        "cost_usd": round(first.cost_usd + second.cost_usd, 3),
        "turns": first.turns + second.turns,
        "agent_error": first.is_error or second.is_error,
        "reply_1": ev1.final_reply[:3000],
        "reply_2": ev2.final_reply[:3000],
    }
