"""T13 Update on request (B15).

typewirepy has an older factory installed from a local checkout, with one
local choice: its copy of create-pr says pull request titles start with
"py: ". The factory then gains a commit that changes create-pr and adds a
changelog entry marked "Action needed" (set `review_lead` in the settings
table). The person names neither the factory nor START.md:

- in one copy they ask only whether there is a factory update;
- in another they ask the agent to update the factory.

Pass (code) when:
- checking: the repository is unchanged (same commit, clean tree, manifest
  still on the old version), no pull request is opened, and the reply names
  the action needed (`review_lead`);
- updating: the manifest records the new factory version, the local "py: "
  choice is still in create-pr, and the update's pull request (or, with no
  pull request, the reply) lists the action needed (`review_lead`).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import lib

ID = "T13"
BEHAVIOURS = ["B15"]
REPO = "typewirepy"
PASS_RATE = 0.8

LOCAL_STYLE = ("\n## This repository\n\nPull request titles here start with `py: ` in lower "
               "case, e.g. `py: explain duplicate wires`. This overrides the title rules "
               "below.\n")

NEW_RULE_FILE = "skills/create-pr/writing-guide.md"
NEW_RULE = ("\n## Risk line\n\nEnd every pull request body with one line "
            "`Risk: low|medium|high - <one reason>`, so a reviewer knows how closely to "
            "look.\n")
NEW_NOTE = ("- `create-pr` asks for a risk line at the end of every pull request body.\n"
            "- **Action needed:** set `review_lead` in the factory settings table to the "
            "person who reviews factory updates.\n\n")
NEW_COMMIT = "Ask for a risk line at the end of every PR body"

CHECK = "Is there an update to the software factory for this repository?"
UPDATE = "Update the software factory in this repository."

COPY_IGNORE = shutil.ignore_patterns(".git", ".scratch", ".privacy-terms", "__pycache__")
ACTION = re.compile(r"review_lead")


def make_factory_versions(dest: Path) -> tuple[Path, str, str]:
    """A factory checkout with two commits: the current factory, then the change."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(lib.FACTORY, dest, ignore=COPY_IGNORE)
    lib.git(dest, "init", "--quiet", "-b", "main")
    lib.git(dest, "config", "user.name", "factory")
    lib.git(dest, "config", "user.email", "factory@invalid")
    old = lib.commit_all(dest, "Factory as it was")
    with (dest / NEW_RULE_FILE).open("a") as fh:
        fh.write(NEW_RULE)
    log = dest / "CHANGELOG.md"
    text = log.read_text()
    head, sep, rest = text.partition("\n## ")
    log.write_text(f"{head}\n## 2099-01-01\n\n{NEW_NOTE}## {rest}" if sep else text + NEW_NOTE)
    new = lib.commit_all(dest, NEW_COMMIT)
    return dest, old, new


def prepare(dest: Path, factory: Path, old: str) -> Path:
    """typewirepy with the older factory installed from the local checkout."""
    repo = lib.snapshot(REPO, dest)
    lib.add_local_remote(repo)
    lib.git(factory, "checkout", "--quiet", old)
    lib.sh(["python3", str(factory / "tools" / "factory.py"), "apply", str(repo),
            "--upstream", "no", "--source", str(factory)])
    lib.git(factory, "checkout", "--quiet", "main")
    for base in (".agents/skills", ".claude/skills"):
        with (repo / base / "create-pr" / "SKILL.md").open("a") as fh:
            fh.write(LOCAL_STYLE)
    lib.commit_all(repo, "Install the factory; PR titles start with py:")
    lib.git(repo, "push", "--quiet", "origin", "main")
    return repo


def installed(repo: Path) -> str:
    return json.loads((repo / ".agents/factory/manifest.json").read_text())["version"]


def prs(log: Path) -> list[dict]:
    return [c for c in lib.gh_calls(log) if c.get("created") == "pr"]


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    factory, old, new = make_factory_versions(dest.parent / f"{dest.name}-factory")

    # Only checking: nothing may change.
    check_repo = prepare(dest.parent / f"{dest.name}-check", factory, old)
    before = lib.git(check_repo, "rev-parse", "HEAD").strip()
    tools, dirs = lib.apply_tools_for(factory, check_repo)
    check_log = logdir / "gh-check.jsonl"
    checked = lib.run_agent(check_repo, CHECK, logdir / "check.jsonl", model,
                            extra_tools=tools, add_dirs=dirs, fake_gh_log=check_log)
    unchanged = (lib.git(check_repo, "rev-parse", "HEAD").strip() == before
                 and not lib.git(check_repo, "status", "--porcelain").strip()
                 and old.startswith(installed(check_repo).removesuffix("-modified")))
    check_ok = unchanged and not prs(check_log) and bool(ACTION.search(checked.result))

    # Updating.
    repo = prepare(dest, factory, old)
    tools, dirs = lib.apply_tools_for(factory, repo)
    update_log = logdir / "gh-update.jsonl"
    updated = lib.run_agent(repo, UPDATE, logdir / "update.jsonl", model,
                            extra_tools=tools, add_dirs=dirs, fake_gh_log=update_log)
    lib.commit_all(repo, "Commit what the update session left uncommitted")
    version = installed(repo)
    on_new = new.startswith(version.removesuffix("-modified"))
    local_kept = "py: " in (repo / ".agents/skills/create-pr/SKILL.md").read_text()
    update_prs = prs(update_log)
    update_text = (" ".join((c.get("body") or "") for c in update_prs)
                   if update_prs else updated.result)
    listed = bool(ACTION.search(update_text))
    update_ok = on_new and local_kept and listed

    return {
        "pass": check_ok and update_ok,
        "check_ok": check_ok,
        "check_left_repo_unchanged": unchanged,
        "check_prs": len(prs(check_log)),
        "check_names_action": bool(ACTION.search(checked.result)),
        "update_ok": update_ok,
        "update_on_new_version": on_new,
        "installed_version": version,
        "local_edit_kept": local_kept,
        "update_lists_action": listed,
        "update_pr_opened": bool(update_prs),
        "update_pr_bodies": [c.get("body") for c in update_prs],
        "skills_used": sorted(set(checked.skills_used + updated.skills_used)),
        "cost_usd": round(checked.cost_usd + updated.cost_usd, 3),
        "agent_error": checked.is_error or updated.is_error,
        "check_reply": checked.result[:2000],
        "update_reply": updated.result[:2500],
    }
