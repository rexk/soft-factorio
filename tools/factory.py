#!/usr/bin/env python3
"""Install or update the factory in a repository, keeping its local edits.

Run it from a checkout of the factory, pointing at the repository:

    python3 <factory>/tools/factory.py plan  <repo> [--upstream yes|no]
    python3 <factory>/tools/factory.py apply <repo> [--upstream yes|no]
                                         [--resolve PATH=ours|theirs ...]

`plan` changes nothing and says what `apply` would do to each file. `apply`
does it and records what it installed in .agents/factory/manifest.json: the
factory's source and version, and a hash of each file as installed. On the
next run, a file whose hash differs from the record has a local edit:

  untouched locally, changed upstream   updated
  edited locally, unchanged upstream    kept, and reported
  edited locally and changed upstream   a conflict: apply stops, changes
                                        nothing, and names the file; rerun
                                        with --resolve PATH=ours (keep the
                                        local edit) or PATH=theirs (take
                                        the factory's version)
  the repository's own skill of the     the repository's skill wins; the
  same name                             factory's is skipped and reported

The rules go into AGENTS.md as one marked block, appended, never rewriting
what's already there. The settings table after the block belongs to the
repository: apply only adds missing keys, and sets `upstream` when told.
The first apply needs --upstream, so the person's answer is recorded.

Python 3, standard library only. Exit codes: 0 done, 1 usage or input
error, 2 unresolved conflicts.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
MANIFEST = ".agents/factory/manifest.json"
SKILL_DIRS = (".agents/skills", ".claude/skills")
GUIDES_DIR = ".agents/factory/guides"
RULES = "AGENTS.md"
BLOCK = "AGENTS.md#soft-factorio"  # the marked block, tracked like a file
BEGIN = "<!-- soft-factorio:begin -->"
END = "<!-- soft-factorio:end -->"
SETTINGS_HEADING = "### Factory settings"


def digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- the factory

def factory_files(factory: Path, upstream: bool) -> dict[str, bytes]:
    """Every path the factory installs, mapped to its content."""
    cfg = json.loads((factory / "factory.json").read_text())
    out: dict[str, bytes] = {}
    for skill in cfg["skills"] + (cfg.get("upstream_skills", []) if upstream else []):
        root = factory / "skills" / skill
        for f in sorted(p for p in root.rglob("*") if p.is_file()):
            for base in SKILL_DIRS:
                out[f"{base}/{skill}/{f.relative_to(root).as_posix()}"] = f.read_bytes()
    guides = factory / "guides"
    if guides.exists():
        for f in sorted(p for p in guides.rglob("*") if p.is_file()):
            out[f"{GUIDES_DIR}/{f.relative_to(guides).as_posix()}"] = f.read_bytes()
    out[BLOCK] = (factory / "rules-block.md").read_text().strip().encode() + b"\n"
    return out


def git_out(repo: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


# The eval ledger (tools/metrics.py) grows with every eval pass. It records the
# factory's versions rather than being part of them, so an uncommitted ledger
# doesn't make a checkout count as modified.
LEDGER = "evals/ledger.jsonl"
NOT_FACTORY_TEXT = f":(top,exclude){LEDGER}"


def factory_version(factory: Path) -> str:
    """The factory's commit; `-modified` if its checkout has uncommitted changes."""
    sha = git_out(factory, "rev-parse", "--short=12", "HEAD")
    if not sha:
        return "unversioned"
    dirty = git_out(factory, "status", "--porcelain", "--", NOT_FACTORY_TEXT)
    return f"{sha}-modified" if dirty else sha


def factory_source(factory: Path) -> str:
    r = subprocess.run(["git", "-C", str(factory), "remote", "get-url", "origin"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "local checkout"


def changes_since(factory: Path, version: str | None) -> list[str]:
    """Titles of the factory's commits since the installed version (none on a first install)."""
    if not version or version == "unversioned":
        return []
    since = version.removesuffix("-modified")
    log = git_out(factory, "log", "--format=- %s", f"{since}..HEAD")
    if log is None:
        return [f"(can't list them: {since} isn't in this checkout of the factory; "
                "clone it with full history)"]
    return log.splitlines()


# ----------------------------------------------------------- the repository

def read_block(repo: Path) -> bytes | None:
    rules = repo / RULES
    if not rules.exists():
        return None
    text = rules.read_text()
    if BEGIN not in text or END not in text:
        return None
    inner = text.split(BEGIN, 1)[1].split(END, 1)[0]
    return inner.strip().encode() + b"\n"


def read_current(repo: Path, path: str) -> bytes | None:
    if path == BLOCK:
        return read_block(repo)
    p = repo / path
    return p.read_bytes() if p.is_file() else None


def load_manifest(repo: Path) -> dict | None:
    p = repo / MANIFEST
    return json.loads(p.read_text()) if p.exists() else None


SETTING_ROW = re.compile(r"^\|\s*`?([\w-]+)`?\s*\|\s*`?([^|`]*?)`?\s*\|\s*$")


def read_settings(repo: Path) -> dict[str, str]:
    rules = repo / RULES
    if not rules.exists():
        return {}
    text = rules.read_text()
    if SETTINGS_HEADING not in text:
        return {}
    settings = {}
    for line in text.split(SETTINGS_HEADING, 1)[1].splitlines()[1:]:
        if line.startswith("#"):
            break
        m = SETTING_ROW.match(line.strip())
        if m and m.group(1) not in ("Key",) and not set(m.group(1)) <= {"-"}:
            settings[m.group(1)] = m.group(2).strip()
    return settings


# ------------------------------------------------------------------ planning

def skill_of(path: str) -> str | None:
    for base in SKILL_DIRS:
        if path.startswith(base + "/"):
            return path[len(base) + 1:].split("/", 1)[0]
    return None


def plan(repo: Path, factory: Path, upstream: bool, resolve: dict[str, str]) -> dict:
    manifest = load_manifest(repo) or {"files": {}}
    recorded: dict[str, str] = manifest["files"]
    incoming = factory_files(factory, upstream)

    # A skill the repository has but the factory never installed is the repository's own.
    own_skills = set()
    for path in incoming:
        skill = skill_of(path)
        if skill and skill not in own_skills:
            dirs = [repo / base / skill for base in SKILL_DIRS]
            installed_by_us = any(skill_of(p) == skill for p in recorded)
            if any(d.exists() for d in dirs) and not installed_by_us:
                own_skills.add(skill)

    steps = []
    for path, data in incoming.items():
        skill = skill_of(path)
        if skill in own_skills:
            steps.append({"path": path, "action": "clash", "skill": skill})
            continue
        up, cur, base = digest(data), digest(read_current(repo, path)), recorded.get(path)
        if base is None:
            action = "unchanged" if cur == up else ("add" if cur is None else "conflict")
        elif cur == base:
            action = "unchanged" if up == base else "update"
        elif up == base or cur == up:
            action = "keep-local" if cur != up else "unchanged"
        else:
            action = "conflict"
        if action == "conflict" and path in resolve:
            action = "update" if resolve[path] == "theirs" else "keep-local"
        steps.append({"path": path, "action": action, "upstream": up})

    for path, base in recorded.items():
        if path not in incoming and skill_of(path) not in own_skills:
            cur = digest(read_current(repo, path))
            if cur is not None:
                steps.append({"path": path, "action": "remove" if cur == base else "keep-removed-upstream"})

    return {
        "from": manifest.get("version"),
        "to": factory_version(factory),
        "steps": steps,
        "incoming": incoming,
        "own_skills": sorted(own_skills),
    }


# ------------------------------------------------------------------ applying

def write_block(repo: Path, content: bytes) -> None:
    rules = repo / RULES
    block = f"{BEGIN}\n{content.decode().rstrip()}\n{END}\n"
    text = rules.read_text() if rules.exists() else "# Agent guidelines\n"
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        tail = rest.split(END, 1)[1]
        text = head + block.rstrip("\n") + tail
    else:
        text = text.rstrip("\n") + "\n\n" + block
    rules.write_text(text)


def write_settings(repo: Path, defaults: dict[str, str], upstream: str | None) -> None:
    rules = repo / RULES
    text = rules.read_text()
    current = read_settings(repo)
    wanted = dict(current)
    for k, v in defaults.items():
        wanted.setdefault(k, v)
    if upstream is not None:
        wanted["upstream"] = upstream
    if wanted == current and SETTINGS_HEADING in text:
        return
    table = "\n".join(
        [SETTINGS_HEADING, "", "| Key | Value |", "|---|---|"]
        + [f"| `{k}` | `{v}` |" for k, v in wanted.items()]
    )
    if SETTINGS_HEADING in text:
        head, rest = text.split(SETTINGS_HEADING, 1)
        lines = rest.splitlines()
        i = 1
        while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("|")):
            i += 1
        text = head + table + "\n" + ("\n" + "\n".join(lines[i:]) if lines[i:] else "")
    else:
        text = text.rstrip("\n") + "\n\n" + table
    rules.write_text(text.rstrip("\n") + "\n")


def apply(repo: Path, factory: Path, result: dict, upstream: str | None, source: str) -> None:
    incoming = result["incoming"]
    files: dict[str, str] = {}
    for step in result["steps"]:
        path, action = step["path"], step["action"]
        if action in ("add", "update"):
            if path == BLOCK:
                write_block(repo, incoming[path])
            else:
                dest = repo / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(incoming[path])
        elif action == "remove":
            (repo / path).unlink()
        if action in ("add", "update", "unchanged", "keep-local"):
            files[path] = step["upstream"]
    cfg = json.loads((factory / "factory.json").read_text())
    write_settings(repo, cfg["settings"], upstream)
    manifest = {
        "source": source,
        "version": result["to"],
        "applied": datetime.date.today().isoformat(),
        "files": dict(sorted(files.items())),
    }
    dest = repo / MANIFEST
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2) + "\n")


# ----------------------------------------------------------------- reporting

LABELS = {
    "add": "added",
    "update": "updated from the factory",
    "keep-local": "kept: local edit",
    "conflict": "CONFLICT: edited locally and changed in the factory",
    "clash": "skipped: the repository has its own skill of this name",
    "remove": "removed: no longer in the factory",
    "keep-removed-upstream": "kept: removed from the factory, but edited locally",
}


def report(result: dict, applied: bool, factory: Path) -> str:
    steps = result["steps"]
    lines = [f"Factory {result['from'] or '(not installed)'} -> {result['to']}"
             + ("" if applied else "  [plan only, nothing changed]")]
    for skill in result["own_skills"]:
        lines.append(f"  The repository's own '{skill}' skill wins; the factory's is not installed.")
    for action, label in LABELS.items():
        paths = [s["path"] for s in steps if s["action"] == action]
        if action == "clash":
            continue
        if paths:
            lines.append(f"{label} ({len(paths)}):")
            lines += [f"  {p}" for p in paths]
    unchanged = sum(s["action"] == "unchanged" for s in steps)
    if unchanged:
        lines.append(f"unchanged: {unchanged} file(s)")
    log = changes_since(factory, result["from"])
    if log:
        lines.append("\nFactory changes since the installed version:")
        lines += log
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["plan", "apply"])
    ap.add_argument("repo", type=Path)
    ap.add_argument("--upstream", choices=["yes", "no"],
                    help="will this repository send lessons upstream? required on first apply")
    ap.add_argument("--resolve", action="append", default=[], metavar="PATH=ours|theirs")
    ap.add_argument("--source", help="where the factory came from, for the manifest")
    ap.add_argument("--factory", type=Path, default=FACTORY, help=argparse.SUPPRESS)
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    args = ap.parse_args(argv)

    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}", file=sys.stderr)
        return 1
    resolve = {}
    for r in args.resolve:
        path, _, choice = r.rpartition("=")
        if choice not in ("ours", "theirs") or not path:
            print(f"--resolve wants PATH=ours or PATH=theirs, got {r!r}", file=sys.stderr)
            return 1
        resolve[path] = choice

    first = load_manifest(repo) is None
    upstream = args.upstream or read_settings(repo).get("upstream")
    if args.command == "apply" and first and args.upstream is None:
        print("First apply: ask the person whether this repository will send lessons "
              "back to the factory, then pass --upstream yes or --upstream no.", file=sys.stderr)
        return 1
    result = plan(repo, args.factory, upstream == "yes", resolve)

    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "incoming"}, indent=2))
    conflicts = [s["path"] for s in result["steps"] if s["action"] == "conflict"]
    if args.command == "apply":
        if conflicts:
            if not args.json:
                print(report(result, False, args.factory))
            print("\nNothing changed. Ask the person about each conflict, then rerun with "
                  "--resolve PATH=ours (keep the local edit) or PATH=theirs (take the "
                  "factory's version).", file=sys.stderr)
            return 2
        apply(repo, args.factory, result, args.upstream, args.source or factory_source(args.factory))
    if not args.json:
        print(report(result, args.command == "apply", args.factory))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
