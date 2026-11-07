"""Shared pieces for scenario evals: snapshots, agent runs, evidence, judges.

Standard library only. A scenario puts an agent in a snapshot of a real
repository, gives it a task, and judges what it did (the git diff, its final
reply, any page it wrote). Nothing here checks that a file merely exists.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
REPOS = json.loads((FACTORY / "evals" / "repos.json").read_text())

# Read-only shell commands an agent may run without a person approving them.
# File edits are allowed through acceptEdits; anything else is denied, as a
# person who isn't there can't approve it.
FAKES = FACTORY / "evals" / "fakes"

# Committing and shipping, for scenarios that end in a pull request or an
# issue. Pushes go to a local bare repository; gh is the fake in evals/fakes.
SHIP_TOOLS = [
    "Bash(git checkout:*)", "Bash(git switch:*)", "Bash(git branch:*)",
    "Bash(git add:*)", "Bash(git commit:*)", "Bash(git push:*)", "Bash(git fetch:*)",
    "Bash(git stash:*)", "Bash(git rebase:*)", "Bash(git merge:*)",
    "Bash(git remote:*)", "Bash(git rev-parse:*)", "Bash(git merge-base:*)",
    "Bash(gh:*)",
    # The snapshot repositories' own check commands, each by name. No general
    # runners (uv run *, pnpm *, npx) and no installs: those run programs
    # nobody has inspected. A check that can't run is reported, not fixed.
    "Bash(uv run pytest:*)", "Bash(uv run ruff:*)", "Bash(pytest:*)",
    "Bash(python -m pytest:*)", "Bash(python3 -m pytest:*)",
    "Bash(pnpm test:*)", "Bash(pnpm lint:*)", "Bash(pnpm check-types:*)",
]

READ_ONLY_BASH = [
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)",
    "Bash(find:*)", "Bash(grep:*)", "Bash(tree:*)", "Bash(pwd)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
    "Bash(git show:*)", "Bash(git ls-files:*)", "Bash(mkdir:*)", "Bash(date:*)",
]


def with_git_dirs(tools: list[str], repo: Path, read_dirs: list[str]) -> list[str]:
    """Add the `git -C <dir>` forms of the allowed git commands.

    Agents often name the repository with -C. Each form names its directory:
    a wildcard before the subcommand would also match `git -C x -c
    core.hooksPath=<script> commit`, which runs a program. The repository gets
    every allowed git command; the other directories (the factory copy) get the
    read-only ones, by absolute path and by path relative to the repository.
    """
    git = [t[len("Bash(git "):] for t in tools if t.startswith("Bash(git ")]
    read_only = {t[len("Bash(git "):] for t in READ_ONLY_BASH if t.startswith("Bash(git ")}
    dirs = [(str(repo), git)]
    for d in read_dirs:
        for spelling in dict.fromkeys([str(d), os.path.relpath(d, repo)]):
            dirs.append((spelling, [g for g in git if g in read_only]))
    return tools + [f"Bash(git -C {d} {g}" for d, subs in dirs for g in subs]


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


def claim_batch(stamp: str) -> str:
    """Reserve runs/<name> and results/<name> in the eval folder for one batch.

    The name is stamp, or stamp.2, stamp.3 and so on when another batch
    (another invocation started in the same second, say) already holds it.
    Both folders are created exclusively, so two batches never share one.
    """
    root = workdir()
    n = 1
    while True:
        name = stamp if n == 1 else f"{stamp}.{n}"
        n += 1
        results, runs = root / "results" / name, root / "runs" / name
        try:
            results.mkdir(parents=True)
        except FileExistsError:
            continue
        try:
            runs.mkdir(parents=True)
        except FileExistsError:  # left by an older batch: give the name up
            results.rmdir()
            continue
        return name


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
        source = cached_clone(spec["url"], workdir() / "cache" / f"{name}@{spec['commit'][:12]}")
    if dest.exists():
        shutil.rmtree(dest)
    sh(["git", "clone", "--quiet", "--no-hardlinks", str(source), str(dest)])
    git(dest, "checkout", "--quiet", "-B", "main", spec["commit"])
    git(dest, "remote", "remove", "origin")
    guard_pushes(dest)
    git(dest, "config", "user.name", "eval-runner")
    git(dest, "config", "user.email", "eval-runner@invalid")
    return dest


_cache_locks: dict[Path, threading.Lock] = {}
_cache_locks_guard = threading.Lock()


def cached_clone(url: str, entry: Path) -> Path:
    """Clone url into the cache folder entry once, safely under parallel runs.

    Threads asking for the same entry wait on one lock, so only one clones.
    The clone goes to a temporary sibling and is renamed into place, so the
    entry never holds a half-made clone, and another process that got there
    first counts as success.
    """
    with _cache_locks_guard:
        lock = _cache_locks.setdefault(entry, threading.Lock())
    with lock:
        if entry.exists():
            return entry
        entry.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(dir=entry.parent, prefix=f".{entry.name}."))
        try:
            sh(["git", "clone", "--quiet", url, str(tmp)])
            try:
                tmp.rename(entry)
            except OSError:
                if not entry.exists():  # not a lost race: a real failure
                    raise
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return entry


def guard_pushes(repo: Path) -> None:
    """Refuse every push except to a local remote inside the eval folder."""
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\n"
        f'case "$2" in "{workdir()}"/*) exit 0;; esac\n'
        "echo 'eval repo: pushing anywhere but the local eval remote is disabled' >&2\n"
        "exit 1\n")
    hook.chmod(0o755)


def add_local_remote(repo: Path) -> Path:
    """Give repo an origin: a bare repository next to it, with main pushed."""
    bare = repo.parent / f"{repo.name}-remote.git"
    if bare.exists():
        shutil.rmtree(bare)
    sh(["git", "init", "--quiet", "--bare", str(bare)])
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "--quiet", "-u", "origin", "HEAD:main")
    return bare


def gh_calls(log: Path) -> list[dict]:
    """What the agent did on the fake GitHub."""
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def empty_repo(dest: Path) -> Path:
    """A new repository with one empty commit and no remote."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git(dest, "init", "--quiet", "-b", "main")
    git(dest, "config", "user.name", "eval-runner")
    git(dest, "config", "user.email", "eval-runner@invalid")
    git(dest, "commit", "--quiet", "--allow-empty", "-m", "Initial commit")
    guard_pushes(dest)
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
    return apply_tools_for(FACTORY)


def agent_apply(repo: Path, logdir: Path, model: str, upstream: str = "no",
                factory: Path = FACTORY, gh_log: Path | None = None) -> AgentRun:
    """A session that applies (or updates) the factory by following its START.md."""
    tools, dirs = apply_tools_for(factory, repo)
    prompt = (f"Apply the software factory to this repository by following "
              f"{factory}/START.md. The factory is the local checkout at {factory}.")
    if upstream:
        prompt += f" My answer to the upstream question: {upstream}."
    run = run_agent(repo, prompt, logdir / "apply.jsonl", model, extra_tools=tools,
                    add_dirs=dirs, fake_gh_log=gh_log)
    (logdir / "apply-reply.txt").write_text(run.result)
    return run


def apply_tools_for(factory: Path, repo: Path | None = None) -> tuple[list[str], list[str]]:
    helpers = [f"{factory}/tools/factory.py"]
    if repo is not None:  # the agent may call the helper by a path relative to the repo
        helpers.append(os.path.relpath(factory / "tools" / "factory.py", repo))
    tools = [
        f"Read({factory}/**)",
        *(f"Bash(python3 {h}:*)" for h in helpers),
        "Bash(git ls-remote:*)",
    ] + SHIP_TOOLS
    return tools, [str(factory)]


@dataclass
class AgentRun:
    result: str
    cost_usd: float
    turns: int
    is_error: bool
    tools_used: list[str] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)


_tool = threading.local()


def use_tool(name: str) -> None:
    """Pick the agent tool for this thread's runs: "claude" (default) or "codex"."""
    _tool.name = name


def agents_started() -> int:
    """How many agent runs this thread has started, to tell setup errors apart."""
    return getattr(_tool, "started", 0)


def run_agent(repo: Path, prompt: str, log: Path, model: str, budget_usd: float = 5.0, **kw) -> "AgentRun":
    _tool.started = agents_started() + 1
    if getattr(_tool, "name", "claude") == "codex":
        return run_codex(repo, prompt, log, **kw)
    return run_claude(repo, prompt, log, model, budget_usd, **kw)


def codex_home() -> Path:
    """A Codex home for evals: the user's login (a symlink), none of their instructions."""
    home = workdir() / "codex-home"
    home.mkdir(parents=True, exist_ok=True)
    auth = home / "auth.json"
    if not auth.exists():
        auth.symlink_to(Path.home() / ".codex" / "auth.json")
    real = Path.home() / ".codex" / "config.toml"
    model = next((l for l in real.read_text().splitlines() if l.startswith("model ")), "") \
        if real.exists() else ""
    (home / "config.toml").write_text(model + "\n")
    return home


_codex_threads: dict[str, str] = {}


def run_codex(repo: Path, prompt: str, log: Path, timeout_s: int = 1800,
              extra_tools: list[str] | None = None, session: str | None = None,
              resume: bool = False, add_dirs: list[str] | None = None,
              fake_gh_log: Path | None = None) -> "AgentRun":
    """One headless Codex turn in repo, sandboxed to the repository (no network)."""
    last = log.with_suffix(".last.txt")
    opts = ["--json", "-o", str(last), "--skip-git-repo-check",
            "-c", 'approval_policy="never"', "-c", 'sandbox_mode="workspace-write"',
            "-c", 'shell_environment_policy.inherit="all"']
    for d in add_dirs or []:
        opts += ["--add-dir", d]
    if session and resume and session in _codex_threads:
        cmd = ["codex", "exec", "resume", _codex_threads[session], *opts, prompt]
    else:
        cmd = ["codex", "exec", *opts, "-C", str(repo), prompt]
    env = dict(os.environ, CODEX_HOME=str(codex_home()))
    if fake_gh_log:
        env["PATH"] = f"{FAKES}{os.pathsep}{env.get('PATH', '')}"
        env["FAKE_GH_LOG"] = str(fake_gh_log)
        origin = git(repo, "remote", "get-url", "origin", check=False).strip()
        if origin.startswith(str(workdir())):
            env["FAKE_GIT_REMOTE"] = origin
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as fh:
        try:
            subprocess.run(cmd, cwd=repo, stdout=fh, stderr=subprocess.STDOUT, env=env,
                           stdin=subprocess.DEVNULL, timeout=timeout_s, text=True)
        except subprocess.TimeoutExpired:
            pass
    error = True
    for line in log.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "thread.started" and session:
            _codex_threads.setdefault(session, ev["thread_id"])
        if ev.get("type") == "turn.completed":
            error = False
    result = last.read_text() if last.exists() else ""
    return AgentRun(result, 0.0, 1, error)


def run_claude(repo: Path, prompt: str, log: Path, model: str, budget_usd: float = 5.0,
              timeout_s: int = 1800, extra_tools: list[str] | None = None,
              session: str | None = None, resume: bool = False,
              add_dirs: list[str] | None = None, fake_gh_log: Path | None = None) -> AgentRun:
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
        "--allowedTools", *with_git_dirs(READ_ONLY_BASH + ["Skill"] + (extra_tools or []),
                                          repo, add_dirs or []),
        "--output-format", "stream-json", "--verbose",
        "--max-budget-usd", str(budget_usd),
    ]
    if add_dirs:
        cmd += ["--add-dir", *add_dirs]
    if session:
        cmd += ["--resume", session] if resume else ["--session-id", session]
    else:
        cmd.append("--no-session-persistence")
    env = dict(os.environ)
    if fake_gh_log:
        env["PATH"] = f"{FAKES}{os.pathsep}{env.get('PATH', '')}"
        env["FAKE_GH_LOG"] = str(fake_gh_log)
        origin = git(repo, "remote", "get-url", "origin", check=False).strip()
        if origin.startswith(str(workdir())):  # a local eval remote: show it as GitHub
            env["FAKE_GIT_REMOTE"] = origin
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as fh:
        try:
            subprocess.run(cmd, cwd=repo, stdout=fh, stderr=subprocess.STDOUT, env=env,
                           stdin=subprocess.DEVNULL, timeout=timeout_s, text=True)
        except subprocess.TimeoutExpired:
            pass
    run = parse_transcript(log)
    if run.is_error and USAGE_LIMIT.search(run.result):
        raise UsageLimit(run.result[:200])
    return run


USAGE_LIMIT = re.compile(r"(?i)hit your .{0,20}limit")


class UsageLimit(Exception):
    """The agent stopped on the account's usage limit: the run says nothing about the factory."""


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


def tool_inputs(log: Path, names: tuple[str, ...]) -> list[dict]:
    """The inputs of every call the agent made to the named tools."""
    found = []
    for line in log.read_text().splitlines() if log.exists() else []:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") in names:
                    found.append(block.get("input", {}))
    return found


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
