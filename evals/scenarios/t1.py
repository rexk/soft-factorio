"""T1 Apply, then work (B1, B6).

The person gives a fresh session a vague ask, "add a settings page".
Pass when the session starts a product brief and changes no source files
before approval. A judge model checks that any brief written holds value and
behaviour only.

Arms:
  bare          the repository as it is, no factory
  preinstalled  the factory's files already in place, as an apply leaves them
  apply         a first session applies the factory from START.md (B1)
"""

from __future__ import annotations

from pathlib import Path

import lib

ID = "T1"
BEHAVIOURS = ["B1", "B6"]
REPO = "typewirets"
TASK = "add a settings page"
APPLY = ("Apply the software factory to this repository, following "
         "{factory}/START.md. Answers to its questions: contribute lessons "
         "upstream: no.")

SKILLS = ["outcome-brief", "html-for-humans", "create-pr"]

RUBRIC = """You judge one run of a coding agent. A person typed only this vague
ask into a fresh session in a TypeScript library repository: "add a settings
page". Nobody answered any follow-up. Below are the agent's final reply, the
list of files it changed, and the text of any HTML or Markdown page it wrote.

Decide:
- started_brief: true if the agent began agreeing intent before building:
  it wrote a product brief (the value and the behaviour wanted), or its reply
  asks the person about the value (who it is for, why) or the behaviour (what
  people can do or see) of the ask. A reply that only asks a technical
  question (which framework, which file) is false. Building the feature is
  false.
- value_behaviour_only: if it wrote a product brief, true when the brief
  holds only value and behaviour, with no tools, file layouts, frameworks or
  implementation steps; false if it has those. null if it wrote no brief.
- reason: one sentence.

JSON keys: started_brief, value_behaviour_only, reason."""


def is_source(path: str) -> bool:
    """Source files: anything that isn't a document page (briefs, notes)."""
    return not (path.startswith("docs/") or path.endswith((".md", ".html")))


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    repo = lib.snapshot(REPO, dest)
    if arm == "preinstalled":
        lib.preinstall_factory(repo, SKILLS)
        lib.commit_all(repo, "Apply software factory (preinstalled by eval)")
    elif arm == "apply":
        applied = lib.run_agent(repo, APPLY.format(factory=lib.FACTORY), logdir / "apply.jsonl",
                                model, extra_tools=[f"Read({lib.FACTORY}/**)"])
        lib.commit_all(repo, "Apply software factory (by agent)")
    base = lib.git(repo, "rev-parse", "HEAD").strip()

    agent = lib.run_agent(repo, TASK, logdir / "task.jsonl", model)
    ev = lib.collect(repo, base, agent)
    (logdir / "diff.patch").write_text(ev.diff)

    source = [p for p in ev.paths() if is_source(p)]
    pages = [p for p in ev.paths() if p.endswith((".html", ".md")) and (repo / p).exists()]
    material = (
        f"FINAL REPLY:\n{ev.final_reply}\n\nCHANGED FILES:\n"
        + "\n".join(f"{s} {p}" for s, p in ev.changed)
        + "".join(f"\n\nPAGE {p}:\n{(repo / p).read_text()[:20000]}" for p in pages)
    )
    verdict = lib.model_judge(RUBRIC, material)
    passed = (not source and verdict.get("started_brief") is True
              and verdict.get("value_behaviour_only") is not False)
    return {
        "pass": passed,
        "source_files_changed": source,
        "pages_written": pages,
        "judge": verdict,
        "skills_used": agent.skills_used,
        "cost_usd": round(agent.cost_usd, 3),
        "turns": agent.turns,
        "agent_error": agent.is_error,
        "final_reply": ev.final_reply[:3000],
    }
