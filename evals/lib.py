"""Shared pieces for scenario evals: snapshots, agent runs, evidence, judges.

Standard library only. A scenario puts an agent in a snapshot of a real
repository, gives it a task, and judges what it did (the git diff, its final
reply, any page it wrote). Nothing here checks that a file merely exists.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
REPOS = json.loads((FACTORY / "evals" / "repos.json").read_text())

# Read-only shell commands an agent may run without a person approving them.
# File edits are allowed through acceptEdits; anything else is denied, as a
# person who isn't there can't approve it.
READ_ONLY_BASH = [
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)",
    "Bash(find:*)", "Bash(grep:*)", "Bash(tree:*)", "Bash(pwd)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
    "Bash(git show:*)", "Bash(git ls-files:*)", "Bash(mkdir:*)", "Bash(date:*)",
]


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True) -> str:
    out = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and out.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {out.stderr.strip()}")
    return out.stdout


def git(repo: Path, *args: str, check: bool = True) -> str:
    return sh(["git", *args], cwd=repo, check=check)


def workdir() -> Path:
    root = Path(os.environ.get("FACTORY_EVAL_DIR") or Path(tempfile.gettempdir()) / "soft-factorio-evals")
    root.mkdir(parents=True, exist_ok=True)
    return root


def snapshot(name: str, dest: Path) -> Path:
    """Copy a repository at its pinned commit into dest, cut off from any remote.

    The source is the local copy at the spec's `path` (relative to the
    factory) when it exists, else a cached clone of its `url`.

    Snapshots are never pushed: the origin remote is removed and a pre-push
    hook refuses every push.
    """
    spec = REPOS[name]
    local = (FACTORY / spec["path"]).resolve() if spec.get("path") else None
    if local and (local / ".git").exists():
        source = local  # a local copy next to the factory; only read, never written
    else:
        source = workdir() / "cache" / f"{name}@{spec['commit'][:12]}"
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            sh(["git", "clone", "--quiet", spec["url"], str(source)])
    if dest.exists():
        shutil.rmtree(dest)
    sh(["git", "clone", "--quiet", "--no-hardlinks", str(source), str(dest)])
    git(dest, "checkout", "--quiet", "-B", "main", spec["commit"])
    git(dest, "remote", "remove", "origin")
    hook = dest / ".git" / "hooks" / "pre-push"
    hook.write_text("#!/bin/sh\necho 'eval snapshot: pushing is disabled' >&2\nexit 1\n")
    hook.chmod(0o755)
    git(dest, "config", "user.name", "eval-runner")
    git(dest, "config", "user.email", "eval-runner@invalid")
    return dest


def empty_repo(dest: Path) -> Path:
    """A new repository with one empty commit and no remote."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git(dest, "init", "--quiet", "-b", "main")
    git(dest, "config", "user.name", "eval-runner")
    git(dest, "config", "user.email", "eval-runner@invalid")
    git(dest, "commit", "--quiet", "--allow-empty", "-m", "Initial commit")
    return dest


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def preinstall_factory(repo: Path, upstream: str = "no") -> None:
    """Install the factory with its helper, as an apply's mechanical part leaves it.

    Used to test the skills on their own, without an agent doing the apply.
    """
    sh([sys.executable, str(FACTORY / "tools" / "factory.py"), "apply", str(repo),
        "--upstream", upstream, "--source", "eval"])


def apply_tools() -> tuple[list[str], list[str]]:
    """Extra tools and directories an agent needs to follow START.md here."""
    tools = [
        f"Read({FACTORY}/**)",
        f"Bash(python3 {FACTORY}/tools/factory.py:*)",
        "Bash(git checkout:*)", "Bash(git switch:*)", "Bash(git branch:*)",
        "Bash(git add:*)", "Bash(git commit:*)", "Bash(git remote:*)",
        "Bash(git -C:*)", "Bash(git ls-remote:*)",
    ]
    return tools, [str(FACTORY)]


@dataclass
class AgentRun:
    result: str
    cost_usd: float
    turns: int
    is_error: bool
    tools_used: list[str] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)


def run_agent(repo: Path, prompt: str, log: Path, model: str, budget_usd: float = 5.0,
              timeout_s: int = 1800, extra_tools: list[str] | None = None,
              session: str | None = None, resume: bool = False,
              add_dirs: list[str] | None = None) -> AgentRun:
    """One headless agent turn in repo. The transcript goes to log.

    For a conversation, pass the same session id each turn, with resume=True
    from the second turn on. Without a session id nothing is persisted.
    """
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--setting-sources", "project,local",  # no personal CLAUDE.md or skills
        "--strict-mcp-config",
        "--permission-mode", "acceptEdits",
        "--allowedTools", *(READ_ONLY_BASH + ["Skill"] + (extra_tools or [])),
        "--output-format", "stream-json", "--verbose",
        "--max-budget-usd", str(budget_usd),
    ]
    if add_dirs:
        cmd += ["--add-dir", *add_dirs]
    if session:
        cmd += ["--resume", session] if resume else ["--session-id", session]
    else:
        cmd.append("--no-session-persistence")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as fh:
        try:
            subprocess.run(cmd, cwd=repo, stdout=fh, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, timeout=timeout_s, text=True)
        except subprocess.TimeoutExpired:
            pass
    return parse_transcript(log)


def parse_transcript(log: Path) -> AgentRun:
    result, cost, turns, err = "", 0.0, 0, True
    tools: list[str] = []
    skills: list[str] = []
    for line in log.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    tools.append(block["name"])
                    if block["name"] == "Skill":
                        skills.append(str(block.get("input", {}).get("skill", "")))
        if ev.get("type") == "result":
            result = ev.get("result") or ""
            cost = float(ev.get("total_cost_usd") or 0)
            turns = int(ev.get("num_turns") or 0)
            err = bool(ev.get("is_error"))
    return AgentRun(result, cost, turns, err, tools, skills)


@dataclass
class Evidence:
    changed: list[tuple[str, str]]  # (status, path) against the baseline commit
    diff: str
    final_reply: str

    def paths(self) -> list[str]:
        return [p for _, p in self.changed]


def collect(repo: Path, base: str, run: AgentRun) -> Evidence:
    """Everything the agent changed since base, committed or not."""
    git(repo, "add", "-A")
    status = git(repo, "diff", "--cached", "--name-status", "--no-renames", base)
    changed = [tuple(l.split("\t", 1)) for l in status.splitlines() if l.strip()]
    diff = git(repo, "diff", "--cached", base)
    return Evidence([(s, p) for s, p in changed], diff, run.result)


def model_judge(rubric: str, material: str, model: str = "sonnet") -> dict:
    """Ask a separate model, in its own session with no tools, to score material.

    The rubric must say to answer with one JSON object. Returns it, or
    {"error": ...} if the reply doesn't parse.
    """
    prompt = (
        f"{rubric}\n\nAnswer with one JSON object and nothing else.\n\n"
        f"<material>\n{material}\n</material>"
    )
    with tempfile.TemporaryDirectory() as empty:
        out = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--setting-sources", "project,local",
             "--strict-mcp-config", "--tools", "", "--output-format", "json",
             "--no-session-persistence"],
            cwd=empty, text=True, capture_output=True, timeout=600, stdin=subprocess.DEVNULL,
        )
    try:
        text = json.loads(out.stdout)["result"]
        start, end = text.index("{"), text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, KeyError) as e:
        return {"error": f"{e}: {out.stdout[:500]} {out.stderr[:500]}"}
