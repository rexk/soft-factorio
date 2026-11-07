#!/usr/bin/env python3
"""This repository's numbers for each factory version it has had, and for the time before.

    python3 .agents/skills/metrics/metrics.py versions
    python3 .agents/skills/metrics/metrics.py compare [VERSION ...] [--html [PATH]]
    python3 .agents/skills/metrics/metrics.py add-reading --about VERSION [VERSION ...] \\
        --author WHO --text TEXT

Every command also takes --repo PATH (default: the repository you are in)
and --ref REF (the history to read, default HEAD). compare also takes
--agent-branch PREFIX (more branch prefixes that mark an agent's pull
request) and --limit N (how many pull requests to read, default 1000).

The numbers are computed on demand from what the repository already holds,
so nothing needs switching on first:

  versions      the history of .agents/factory/manifest.json says which
                factory version the repository had when. The time before
                its first apply is its own version, "before-the-factory".
  pull requests `gh pr list` (read only), split by when each was opened.
  corrections   the retro skill's Lessons tables in agent pull requests.
  reverts       "This reverts commit ..." in the git history.

Only readings are stored: add-reading appends them to
.agents/metrics/ledger.jsonl, committed with the repository and never
rewritten. `compare` prints JSON; `--html` also writes a page (default
.scratch/metrics/repository.html, kept out of git).

The numbers carry no verdict. Nothing here scores, ranks, passes or fails a
version, and nothing is compared across repositories or people: the exit
code is 0 whatever the numbers are, and 1 only for a usage error. Nothing
is pushed, posted or sent anywhere. Python 3, standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics_ledger import (append, cell, compare_rows, inside, mean, median,  # noqa: E402
                            now, read, reading, readings_about, render, select)

MANIFEST = ".agents/factory/manifest.json"
LEDGER = ".agents/metrics/ledger.jsonl"
DEFAULT_PAGE = ".scratch/metrics/repository.html"
BEFORE = "before-the-factory"
WITHOUT = "without-the-factory"  # the manifest was removed after an apply
REVERT_DAYS = 14
PR_LIMIT = 1000

# K1: which pull requests are an agent's. A rough rule, stated as the source of every number it feeds.
AGENT_BRANCHES = ("claude/", "codex/", "copilot/", "cursor/", "devin/")
AGENT_MARK = re.compile(
    r"generated with \[?claude code"
    r"|co-authored-by:[^\n]*\b(claude|copilot|codex|cursor|devin|aider|gemini)\b", re.I)
AGENT_MARK_TEXT = ("Generated with Claude Code; Co-Authored-By: Claude, Copilot, Codex, Cursor, "
                   "Devin, Aider or Gemini")
PR_FIELDS = "number,body,headRefName,state,createdAt,mergedAt,mergeCommit,reviews,commits"

PRS, LESSONS, HISTORY = "agent pull requests", "corrections", "reverts"
GROUPS = [PRS, LESSONS, HISTORY]
DEFINITIONS = {
    "agent_prs_opened": "Agent pull requests opened in this version, whatever happened to them since.",
    "agent_prs_merged": "Agent pull requests opened in this version that were merged.",
    "agent_prs_closed_unmerged": "Agent pull requests opened in this version that were closed without merging.",
    "agent_prs_still_open": "Agent pull requests opened in this version that are open now.",
    "agent_pr_merge_rate": "Merged agent pull requests divided by those decided (merged, or closed "
                           "without merging). Open ones are left out.",
    "review_rounds_per_merged_pr": "Reviews that requested changes or left comments before the merge, "
                                   "mean per merged agent pull request. Approvals are not counted.",
    "hours_to_merge_median": "Median hours from opening to merging, over merged agent pull requests.",
    "reverted_within_14_days": "Merged agent pull requests whose merge commit a later commit reverted "
                               "(\"This reverts commit ...\") within 14 days of the merge.",
    "agent_prs_with_lessons_table": "Agent pull requests whose description holds a retro Lessons table "
                                    "(a table with Correction and Fix columns).",
    "corrections_per_pr": "Lessons table rows, mean per agent pull request that has a table. One without "
                          "a table is left out, not counted as 0.",
    "corrections_with_a_fix": "Lessons table rows whose Fix column names a test, a rule or a skill, "
                              "rather than nothing.",
    "revert_commits": "Commits dated in this version whose message says \"This reverts commit\", "
                      "whoever made them.",
}
GROUP_OF = {m: HISTORY if m == "revert_commits" else LESSONS if "lessons" in m or "correction" in m else PRS
            for m in DEFINITIONS}
ABSENT = "not computed for this version"


# --------------------------------------------------------------------- git

def git(repo: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def when(stamp: str) -> datetime.datetime:
    t = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def day(t: datetime.datetime | None) -> str:
    return t.date().isoformat() if t else "now"


def commits_of(repo: Path, ref: str) -> list[dict]:
    """Every commit reachable from ref: sha, committer date and message."""
    out = git(repo, "log", "--format=%H%x1f%cI%x1f%B%x1e", ref, "--")
    if out is None:
        raise ValueError(f"can't read the history of {ref!r}: run this in a git repository with commits")
    commits = []
    for rec in out.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) == 3:
            commits.append({"sha": parts[0], "date": when(parts[1]), "message": parts[2]})
    if not commits:
        raise ValueError(f"{ref!r} has no commits yet")
    return commits


def manifest_version(repo: Path, sha: str) -> str | None:
    text = git(repo, "show", f"{sha}:{MANIFEST}")
    if text is None:
        return None
    try:
        return str(json.loads(text).get("version") or "unversioned")
    except (json.JSONDecodeError, AttributeError):
        return "unreadable-manifest"


def versions(repo: Path, ref: str, commits: list[dict]) -> list[dict]:
    """The factory versions the repository had, oldest first, with the time before its first apply.

    A version starts with the commit on ref's first-parent line that put it
    in the manifest and lasts until the next one. A version applied twice
    (say, after a step back) has both spans.
    """
    log = git(repo, "log", "--first-parent", "--reverse", "--format=%H %cI", ref, "--", MANIFEST) or ""
    starts = [(min(c["date"] for c in commits), BEFORE, None)]
    for line in log.splitlines():
        sha, stamp = line.split(" ", 1)
        version = manifest_version(repo, sha)
        key = version or WITHOUT
        if key != starts[-1][1]:
            starts.append((when(stamp), key, sha))
    if len(starts) > 1 and starts[1][0] <= starts[0][0]:
        starts.pop(0)  # the repository started with the factory: no time before it
    src = f"git log --first-parent {ref} -- {MANIFEST}"
    out: dict[str, dict] = {}
    for i, (start, key, sha) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else None
        v = out.setdefault(key, {
            "version": key,
            "factory_version": None if key in (BEFORE, WITHOUT) else key,
            "label": {BEFORE: "before the factory", WITHOUT: "without the factory"}.get(key, key),
            "spans": [], "manifest_commits": [], "source": src})
        v["spans"].append({"from": start.isoformat(timespec="minutes"),
                           "to": end.isoformat(timespec="minutes") if end else None})
        if sha:
            v["manifest_commits"].append(sha[:12])
    return list(out.values())


def spans_of(version: dict) -> list[tuple]:
    return [(when(s["from"]), when(s["to"]) if s["to"] else None) for s in version["spans"]]


def within(t: datetime.datetime, spans: list[tuple]) -> bool:
    return any(start <= t and (end is None or t < end) for start, end in spans)


def span_text(version: dict) -> str:
    return "; ".join(f"{day(a)} to {day(b)}" for a, b in spans_of(version))


# ----------------------------------------------------------- pull requests

def pull_requests(repo: Path, limit: int) -> tuple[list | None, str]:
    """The repository's pull requests from `gh pr list` (read only), or None and why not."""
    gh = shutil.which("gh")
    if not gh:
        return None, "gh (the GitHub CLI) isn't installed, so pull request numbers are missing"
    r = subprocess.run([gh, "pr", "list", "--state", "all", "--limit", str(limit), "--json", PR_FIELDS],
                       cwd=repo, capture_output=True, text=True,
                       env=dict(os.environ, GH_PROMPT_DISABLED="1"))
    reason = (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[0]
    if r.returncode != 0:
        return None, f"gh pr list failed ({reason}), so pull request numbers are missing"
    try:
        prs = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, "gh pr list printed something that isn't JSON, so pull request numbers are missing"
    src = f"gh pr list --state all --limit {limit}"
    if len(prs) >= limit:
        src += f" (the newest {limit} only: older ones weren't read, raise --limit)"
    return prs, src


def agent_rule(branches: tuple) -> str:
    return (f"agent pull request: its head branch starts with {', '.join(branches)}, or its description "
            f"or a commit message carries an agent footer or co-author trailer ({AGENT_MARK_TEXT})")


def is_agents(pr: dict, branches: tuple) -> bool:
    if (pr.get("headRefName") or "").startswith(branches):
        return True
    texts = [pr.get("body") or ""] + [f"{c.get('messageHeadline') or ''}\n{c.get('messageBody') or ''}"
                                      for c in pr.get("commits") or []]
    return any(AGENT_MARK.search(t) for t in texts)


def table_cells(line: str) -> list[str] | None:
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))]


def lessons(body: str | None) -> list[list[str]] | None:
    """K3: the rows of the Lessons tables in a description, or None when there is none.

    A Lessons table is a markdown table whose header has a column starting
    "Correction" and one starting "Fix", as the retro skill writes it. Each
    row is returned as [correction, fix].
    """
    lines = (body or "").splitlines()
    rows, found, i = [], False, 0
    while i < len(lines):
        head = table_cells(lines[i])
        sep = table_cells(lines[i + 1]) if i + 1 < len(lines) else None
        if head and sep and all(re.fullmatch(r":?-+:?", c) for c in sep):
            low = [c.lower() for c in head]
            fix = next((n for n, c in enumerate(low) if c.startswith("fix")), None)
            if any(c.startswith("correction") for c in low) and fix is not None:
                found, i = True, i + 2
                while i < len(lines) and (cells := table_cells(lines[i])) is not None:
                    row = [cells[0], cells[fix] if fix < len(cells) else ""]
                    if any(row) and row not in rows:
                        rows.append(row)
                    i += 1
                continue
        i += 1
    return rows if found else None


def names_a_fix(fix: str) -> bool:
    low = fix.lower().strip(" *_`")
    if not low or low.startswith(("nothing", "none", "n/a", "no fix")) or low in ("-", "—"):
        return False
    return bool(re.search(r"\b(tests?|rules?|skills?)\b", low))


def listed(numbers: list[int]) -> str:
    if not numbers:
        return "none"
    shown = ", ".join(f"#{n}" for n in numbers[:30])
    return shown + (f" and {len(numbers) - 30} more" if len(numbers) > 30 else "")


# ----------------------------------------------------------------- numbers

def reverts_in(commits: list[dict]) -> list[tuple[str, datetime.datetime]]:
    return [(m.group(1), c["date"]) for c in commits
            for m in re.finditer(r"This reverts commit ([0-9a-f]{7,40})", c["message"])]


def numbers_of(version: dict, prs: list | None, pr_source: str, commits: list[dict],
               branches: tuple, ref: str) -> dict[str, dict]:
    """Group -> metric -> cell, for one version."""
    spans = spans_of(version)
    period = span_text(version)
    out: dict[str, dict] = {}

    dated = [c for c in commits if within(c["date"], spans)]
    reverts = reverts_in(commits)
    out[HISTORY] = {"revert_commits": cell(len(reverts_in(dated)), len(dated),
                                           f"git log {ref}: the {len(dated)} commits dated {period}")}

    if prs is None:
        for group in (PRS, LESSONS):
            out[group] = {m: cell(None, 0, pr_source) for m, g in GROUP_OF.items() if g == group}
        return out

    opened = [p for p in prs if p.get("createdAt") and within(when(p["createdAt"]), spans)]
    agent = sorted((p for p in opened if is_agents(p, branches)), key=lambda p: p["number"])
    merged = [p for p in agent if p.get("mergedAt")]
    closed = [p for p in agent if not p.get("mergedAt") and p.get("state") == "CLOSED"]
    still = [p for p in agent if p not in merged and p not in closed]
    decided = len(merged) + len(closed)
    src = (f"{pr_source}; {agent_rule(branches)}; opened {period}: "
           f"{listed([p['number'] for p in agent])}")

    def rounds(p):
        merged_at = when(p["mergedAt"])
        return sum(1 for r in p.get("reviews") or []
                   if r.get("state") in ("CHANGES_REQUESTED", "COMMENTED")
                   and (not r.get("submittedAt") or when(r["submittedAt"]) <= merged_at))

    hours = [(when(p["mergedAt"]) - when(p["createdAt"])).total_seconds() / 3600 for p in merged]
    with_sha = [p for p in merged if (p.get("mergeCommit") or {}).get("oid")]

    def reverted(p):
        sha, merged_at = p["mergeCommit"]["oid"], when(p["mergedAt"])
        return any((sha.startswith(t) or t.startswith(sha))
                   and d - merged_at <= datetime.timedelta(days=REVERT_DAYS) for t, d in reverts)

    out[PRS] = {
        "agent_prs_opened": cell(len(agent), len(opened), src),
        "agent_prs_merged": cell(len(merged), len(agent), src),
        "agent_prs_closed_unmerged": cell(len(closed), len(agent), src),
        "agent_prs_still_open": cell(len(still), len(agent), src),
        "agent_pr_merge_rate": cell(len(merged) / decided if decided else None, decided, src),
        "review_rounds_per_merged_pr": cell(mean([rounds(p) for p in merged]), len(merged), src),
        "hours_to_merge_median": cell(median(hours), len(merged), src, 1),
        "reverted_within_14_days": cell(sum(map(reverted, with_sha)) if with_sha else None, len(with_sha),
                                        f"{src}; reverts from git log {ref}"),
    }

    tables = {p["number"]: rows for p in agent if (rows := lessons(p.get("body"))) is not None}
    rows = [r for t in tables.values() for r in t]
    lsrc = f"Lessons tables in the descriptions of agent pull requests {listed(sorted(tables))} ({src})"
    out[LESSONS] = {
        "agent_prs_with_lessons_table": cell(len(tables), len(agent), lsrc),
        "corrections_per_pr": cell(mean([len(t) for t in tables.values()]), len(tables), lsrc),
        "corrections_with_a_fix": cell(sum(names_a_fix(r[1]) for r in rows) if tables else None,
                                       len(rows), lsrc),
    }
    return out


def compare(repo: Path, ref: str = "HEAD", wanted: list[str] | None = None,
            branches: tuple = AGENT_BRANCHES, limit: int = PR_LIMIT) -> dict:
    """Each chosen version's numbers next to the others', with the changes between them."""
    commits = commits_of(repo, ref)
    chosen = select(versions(repo, ref, commits), wanted or [])
    prs, pr_source = pull_requests(repo, limit)
    keys = [v["version"] for v in chosen]
    nums = {v["version"]: numbers_of(v, prs, pr_source, commits, branches, ref) for v in chosen}
    rows = compare_rows(keys, nums, DEFINITIONS.__getitem__, list(DEFINITIONS), ABSENT, GROUPS)
    applied = any(v["factory_version"] for v in chosen)
    return {
        "about": ("This repository's numbers before the factory and for each factory version it has "
                  "applied, computed now from its git history and pull requests. Each change is the "
                  "difference from the version before it in this list. No number here is a score or "
                  "a verdict, and nothing is compared across repositories or people: what the numbers "
                  "mean is for readers to write down as readings."
                  + ("" if applied else " This repository hasn't applied the factory yet.")),
        "ledger": LEDGER,
        "as_of": {"ref": (git(repo, "rev-parse", "--short=12", ref) or ref).strip(), "date": now()},
        "agent_rule": agent_rule(branches),
        "versions": chosen,
        "rows": rows,
        "readings": readings_about(read(repo / LEDGER), keys),
    }


# ---------------------------------------------------------------------- page

def short(key: str) -> str:
    if key in (BEFORE, WITHOUT):
        return key.replace("-", " ")
    sha, dash, rest = key.partition("-")
    return sha[:7] + (f"-{rest}" if dash else "")


def page(data: dict, command: str) -> str:
    e = html.escape

    def cells(v: dict) -> list[str]:
        return [e(span_text(v)), e(", ".join(v["manifest_commits"]) or "none"), e(v["source"])]

    return render({
        "title": f"This repository's numbers for {len(data['versions'])} versions, side by side",
        "author": "the metrics skill", "absent": ABSENT,
        "takeaway": ("Each version's numbers sit next to the version before it, with the change between "
                     "them. A change is a difference, not a verdict: what the numbers mean is for you to "
                     "say, and the readings people and agents wrote are at the end."),
        "versions_intro": ("The factory versions this repository has had, oldest first, from the history of "
                           f"<code>{MANIFEST}</code>. <code>{BEFORE}</code> is the time before its first "
                           "apply."),
        "version_headers": ["Dates", "Manifest commits", "Source"], "version_cells": cells,
        "short": short, "numbers_heading": "Numbers, by kind",
        "numbers_intro": ("Every number for every version shown; <i>n</i> is how many pull requests, rows or "
                          "commits a number rests on. A pull request counts in the version it was opened "
                          "in. Definitions and sources, including the rule that tells an agent's pull "
                          f"request from a person's, are under each table. Agent rule: {e(data['agent_rule'])}."),
        "add_reading": f"python3 {command} add-reading --about VERSION --author WHO --text TEXT",
        "json_command": f"python3 {command} compare",
    }, data)


# ----------------------------------------------------------------------- cli

def write_page(repo: Path, rel: str, text: str) -> None:
    dest = repo / rel
    if not inside(dest, repo):
        raise ValueError(f"the page must go inside the repository: {rel}")
    if rel == DEFAULT_PAGE and not dest.parent.exists():
        dest.parent.mkdir(parents=True)
        (dest.parent / ".gitignore").write_text("*\n")  # a throwaway page: keep it out of commits
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)


def main(argv: list[str]) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", type=Path, help="the repository (default: the one you are in)")
    common.add_argument("--ref", default="HEAD", help="the history to read (default HEAD)")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("versions", parents=[common], help="the factory versions this repository has had, as JSON")
    c = sub.add_parser("compare", parents=[common], help="versions side by side, as JSON")
    c.add_argument("version", nargs="*", help="version keys or prefixes (default: all)")
    c.add_argument("--html", nargs="?", const=DEFAULT_PAGE, metavar="PATH",
                   help=f"also write the page (default {DEFAULT_PAGE})")
    c.add_argument("--agent-branch", action="append", default=[], metavar="PREFIX",
                   help="another head-branch prefix that marks an agent's pull request")
    c.add_argument("--limit", type=int, default=PR_LIMIT, help=f"pull requests to read (default {PR_LIMIT})")
    r = sub.add_parser("add-reading", parents=[common], help="append a reading about one or more versions")
    r.add_argument("--about", nargs="+", required=True, metavar="VERSION")
    r.add_argument("--author", required=True, help="who wrote it: a role or an agent, not contact details")
    r.add_argument("--text", required=True)
    args = ap.parse_args(argv)

    try:
        top = git(args.repo or Path.cwd(), "rev-parse", "--show-toplevel")
        if not top:
            raise ValueError("run this inside a git repository, or pass --repo")
        repo = Path(top.strip())
        here = Path(__file__).resolve()
        command = here.relative_to(repo.resolve()).as_posix() if inside(here, repo) else str(here.name)
        if args.command == "versions":
            print(json.dumps(versions(repo, args.ref, commits_of(repo, args.ref)), indent=1))
        elif args.command == "compare":
            branches = AGENT_BRANCHES + tuple(b for b in args.agent_branch if b not in AGENT_BRANCHES)
            data = compare(repo, args.ref, args.version, branches, max(1, args.limit))
            if args.html:
                write_page(repo, args.html, page(data, command))
                print(f"page: {args.html}", file=sys.stderr)
            print(json.dumps(data, indent=1))
        elif args.command == "add-reading":
            all_versions = versions(repo, args.ref, commits_of(repo, args.ref))
            about = [v["version"] for v in select(all_versions, args.about)]
            ref = (git(repo, "rev-parse", "--short=12", args.ref) or args.ref).strip()
            entry = reading(about, args.author, args.text, ref=ref)
            append(repo / LEDGER, [entry])
            print(json.dumps(entry, indent=1))
    except ValueError as err:
        print(f"metrics: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
