"""T3 Update keeps local choices (B3).

typewirepy has an older factory installed, with one local choice: its copy of
create-pr says pull request titles start with "py: ". The newer factory
changes create-pr to ask for a "Risk:" line in every pull request body. An
agent updates the factory from START.md (the person then merges that update),
and a fresh session ships a small change.

Pass when the change's pull request title follows the local style ("py: "),
its body follows the newer factory (a "Risk:" line), and the update's pull
request lists what changed in the factory (it mentions the risk line). Code
only.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import lib

ID = "T3"
BEHAVIOURS = ["B3"]
REPO = "typewirepy"
PASS_RATE = 0.8

LOCAL_STYLE = ("\n## This repository\n\nPull request titles here start with `py: ` in lower "
               "case, e.g. `py: explain duplicate wires`. This overrides the title rules "
               "below.\n")

NEW_RULE_FILE = "skills/create-pr/writing-guide.md"
NEW_RULE = ("\n## Risk line\n\nEnd every pull request body with one line "
            "`Risk: low|medium|high - <one reason>`, so a reviewer knows how closely to "
            "look.\n")
NEW_COMMIT = "Ask for a risk line at the end of every PR body"

TASK = ("The NotResolvedError message should tell the user to resolve the wire (for "
        "example with get_instance) before calling get_cached. Make that change and ship "
        "it for review.")

COPY_IGNORE = shutil.ignore_patterns(".git", ".scratch", ".privacy-terms", "__pycache__")


def make_factory_versions(dest: Path) -> tuple[Path, str, str]:
    """A factory checkout with two commits: the current factory, then the new rule."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(lib.FACTORY, dest, ignore=COPY_IGNORE)
    lib.git(dest, "init", "--quiet", "-b", "main")
    lib.git(dest, "config", "user.name", "factory")
    lib.git(dest, "config", "user.email", "factory@invalid")
    old = lib.commit_all(dest, "Factory as it was")
    with (dest / NEW_RULE_FILE).open("a") as fh:
        fh.write(NEW_RULE)
    new = lib.commit_all(dest, NEW_COMMIT)
    return dest, old, new


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    factory, old, new = make_factory_versions(dest.parent / f"{dest.name}-factory")
    repo = lib.snapshot(REPO, dest)
    lib.add_local_remote(repo)

    # Install the older factory, then make the repository's local choice.
    lib.git(factory, "checkout", "--quiet", old)
    lib.sh(["python3", str(factory / "tools" / "factory.py"), "apply", str(repo),
            "--upstream", "no", "--source", "eval"])
    lib.git(factory, "checkout", "--quiet", "main")
    for base in (".agents/skills", ".claude/skills"):
        with (repo / base / "create-pr" / "SKILL.md").open("a") as fh:
            fh.write(LOCAL_STYLE)
    lib.commit_all(repo, "Install the factory; PR titles start with py:")
    lib.git(repo, "push", "--quiet", "origin", "main")

    # The update, by an agent following the newer START.md.
    update_log = logdir / "gh-update.jsonl"
    updated = lib.agent_apply(repo, logdir, model, upstream="", factory=factory, gh_log=update_log)
    lib.commit_all(repo, "Commit what the update session left uncommitted")
    branch = lib.git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != "main":  # the person merges the update
        lib.git(repo, "checkout", "--quiet", "main")
        lib.git(repo, "merge", "--quiet", "--no-edit", branch)

    # A fresh session ships a change.
    task_log = logdir / "gh-task.jsonl"
    agent = lib.run_agent(repo, TASK, logdir / "task.jsonl", model,
                          extra_tools=lib.SHIP_TOOLS, fake_gh_log=task_log)

    update_prs = [c for c in lib.gh_calls(update_log) if c.get("created") == "pr"]
    update_text = " ".join((c.get("body") or "") for c in update_prs) + " " + updated.result
    task_prs = [c for c in lib.gh_calls(task_log) if c.get("created") == "pr"]
    title_ok = bool(task_prs) and all((c.get("title") or "").startswith("py: ") for c in task_prs)
    body_ok = bool(task_prs) and all(re.search(r"(?mi)^\W*risk:", c.get("body") or "")
                                     for c in task_prs)
    listed = bool(re.search(r"(?i)risk", update_text))
    local_kept = "py: " in (repo / ".agents/skills/create-pr/SKILL.md").read_text()
    return {
        "pass": title_ok and body_ok and listed,
        "title_follows_local_style": title_ok,
        "body_follows_new_factory": body_ok,
        "update_lists_change": listed,
        "update_pr_opened": bool(update_prs),
        "local_edit_still_in_file": local_kept,
        "task_pr_titles": [c.get("title") for c in task_prs],
        "task_pr_bodies": [c.get("body") for c in task_prs],
        "update_pr_bodies": [c.get("body") for c in update_prs],
        "cost_usd": round(agent.cost_usd + updated.cost_usd, 3),
        "agent_error": agent.is_error or updated.is_error,
        "final_reply": agent.result[:2000],
        "update_reply": updated.result[:2500],
    }
