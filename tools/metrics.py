#!/usr/bin/env python3
"""The factory's eval numbers over time: a ledger, a comparison, and readings.

    python3 tools/metrics.py versions
    python3 tools/metrics.py compare [VERSION ...] [--html [PATH]]
    python3 tools/metrics.py add-reading --about VERSION [VERSION ...] --author WHO --text TEXT
    python3 tools/metrics.py import-results FILE

The ledger, evals/ledger.jsonl, is committed and append-only: one JSON object
per line, never rewritten. evals/run.py appends an entry after every eval
pass and every --calibrate; add-reading appends a reading.

A version is the factory's commit as factory_version() reports it, with
`-modified` for a checkout with uncommitted changes. Uncommitted states on
one commit are told apart by `state`, so a version's key is VERSION, or
VERSION+STATE for an uncommitted one.

`versions` and `compare` print JSON. `compare` puts each version's numbers
next to the others', each with what it counts, where it came from and how
many runs it rests on, and the change from the last earlier version that ran
the same scenario and arm. A number a version doesn't have is null with
"missing": true, never 0. `--html` also writes the comparison as a page
(default .scratch/metrics/compare.html).

The numbers carry no verdict. Nothing here scores, ranks, passes or fails a
version: the exit code is 0 whatever the numbers are, and 1 only for a usage
error. What they mean is for each reader to write down as a reading.

Everything is read from and written to this repository only: nothing is
pushed, posted or sent anywhere. Python 3, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
# The ledger code is shared with the metrics skill, which ships it to adopting repositories.
sys.path.append(str(FACTORY / "skills" / "metrics"))
from factory import LEDGER, NOT_FACTORY_TEXT, factory_version, git_out  # noqa: E402
from metrics_ledger import (MAX_READING, append, cell, compare_rows, inside, mean,  # noqa: E402,F401
                            now, read, reading, readings_about, render as render_page, select as pick)

DEFAULT_PAGE = ".scratch/metrics/compare.html"

# What each number counts. Every number in the output carries its row's definition.
DEFINITIONS = {
    "runs": "Runs that were judged, pass or fail. Void runs (cut short before they could be judged) are not counted.",
    "passed": "Runs the scenario's judge passed.",
    "pass_rate": "Passed runs divided by judged runs.",
    "void": "Runs voided: a usage limit or a setup error stopped them before an agent's work could be judged.",
    "crashed": "Runs that raised an error after an agent had started; the runner counts them as failed.",
    "pass_mark": "The share of runs the scenario itself asks to pass, as the runner recorded it. Set by the scenario, not by these metrics.",
    "cost_per_run_usd": "Mean agent cost in US dollars per run, as the scenario reported it (judge calls not included).",
    "cost_per_passing_run_usd": "Mean agent cost in US dollars per passing run.",
    "seconds_per_run": "Mean wall-clock seconds per run.",
    "turns_per_run": "Mean agent turns per run, summed over the run's agent sessions.",
    "turns_per_passing_run": "Mean agent turns per passing run.",
    "lift_over_bare": "This arm's pass rate minus the bare arm's, in the same version (the bare arm runs without the factory).",
    "judge_samples": "Calibration samples the scenario's judge was checked against (evals/run.py --calibrate).",
    "judge_agreed": "Calibration samples where the judge's answer matched the sample's known answer.",
}
ABSENT = "this version has no runs of this scenario and arm"
SKILL_METRIC = "runs_using_skill:"
SKILL_DEFINITION = "Runs in which an agent used the {skill} skill, out of the runs whose skills were recorded."


# ------------------------------------------------------------------ the ledger

def ledger_path(root: Path = FACTORY) -> Path:
    return root / LEDGER


def key_of(entry: dict) -> str:
    return entry["version"] + (f"+{entry['state']}" if entry.get("state") else "")


# -------------------------------------------------------- versions and states

def factory_state(factory: Path) -> str | None:
    """For an uncommitted checkout, a short hash of its changes; None when clean.

    Two passes on the same commit with different uncommitted changes get
    different states, so they are never pooled as one version.
    """
    if not factory_version(factory).endswith("-modified"):
        return None
    h = hashlib.sha256()
    r = subprocess.run(["git", "-C", str(factory), "diff", "HEAD", "--binary", "--", NOT_FACTORY_TEXT],
                       capture_output=True)
    h.update(r.stdout)
    others = git_out(factory, "ls-files", "--others", "--exclude-standard", "-z", "--", NOT_FACTORY_TEXT)
    for name in sorted(p for p in (others or "").split("\0") if p):
        h.update(name.encode() + b"\0")
        f = factory / name
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


def run_row(r: dict) -> dict:
    """The numbers the ledger keeps from one run's result: no judge text, no replies."""
    void = r.get("void")
    return {
        "scenario": r["scenario"], "arm": r["arm"], "run": r.get("run"),
        "pass": r.get("pass"),
        "void": void.split(":", 1)[0] if isinstance(void, str) else False,
        "crashed": "error" in r,
        "cost_usd": r.get("cost_usd"),
        "seconds": r.get("seconds"),
        "turns": r.get("agent_turns"),
        "skills": r.get("agent_skills"),
    }


def record_pass(stamp: str, model: str, results: list[dict], summary: dict,
                factory: Path = FACTORY) -> dict:
    """Append one eval pass to the factory's ledger; returns the entry."""
    entry = {
        "kind": "pass", "id": stamp,
        "version": factory_version(factory), "state": factory_state(factory),
        "date": now(), "model": model, "source": "evals/run.py",
        "pass_marks": {k: s["rate"] for k, s in summary.items()},
        "runs": [run_row(r) for r in results],
    }
    append(ledger_path(factory), [entry])
    return entry


def record_calibration(stamp: str, judges: dict, factory: Path = FACTORY) -> dict:
    """Append one --calibrate check: per scenario, samples and how many the judge agreed with."""
    entry = {
        "kind": "calibration", "id": stamp,
        "version": factory_version(factory), "state": factory_state(factory),
        "date": now(), "source": "evals/run.py --calibrate", "judges": judges,
    }
    append(ledger_path(factory), [entry])
    return entry


# ------------------------------------------------------------------- import

def commit_before(factory: Path, stamp: str) -> str | None:
    """The newest commit authored at or before a runner timestamp (YYYYMMDD-HHMMSS)."""
    log = git_out(factory, "log", "--format=%H %ad", "--date=format:%Y%m%d-%H%M%S", "HEAD")
    for line in (log or "").splitlines():
        sha, when = line.split(" ", 1)
        if when <= stamp:
            return git_out(factory, "rev-parse", "--short=12", sha)
    return None


def import_results(path: Path, factory: Path = FACTORY) -> list[dict]:
    """Turn a hand-picked results file (passes with notes) into ledger entries.

    The file doesn't say which factory text each pass ran on. The version is
    inferred as the last commit before the pass started, `-modified` because
    the change under test hadn't landed yet, with the start time as its state
    since the uncommitted changes weren't recorded. Each note becomes a
    reading. Passes already in the ledger are skipped.
    """
    data = json.loads(path.read_text())
    try:
        source = path.resolve().relative_to(factory.resolve()).as_posix()
    except ValueError:
        source = path.name
    have = {e.get("id") for e in read(ledger_path(factory))}
    entries = []
    for p in data["passes"]:
        stamp = f"{p['started']}-{p['pass']}"
        if stamp in have:
            continue
        sha = commit_before(factory, p["started"])
        if sha is None:
            raise ValueError(f"no commit before {p['started']}: import from a full clone")
        void_recorded = all("void" in s for s in p["summary"].values())
        runs = []
        for r in p["runs"]:
            row = run_row(r)
            if not void_recorded and r.get("pass") is not None:
                row["void"] = None  # the runner didn't tell void runs apart yet
            row["skills"] = r.get("skills_used")
            runs.append(row)
        s = p["started"]
        entry = {
            "kind": "pass", "id": stamp, "version": f"{sha}-modified", "state": s,
            "date": f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}",
            "model": data.get("model"), "source": f"imported from {source}",
            "version_note": ("inferred: the last commit before the pass started, -modified "
                             "because the change under test hadn't landed; the start time "
                             "stands in for the uncommitted changes, which weren't recorded"),
            "pass_marks": {k: v["rate"] for k, v in p["summary"].items()},
            "runs": runs,
        }
        entries.append(entry)
        if p.get("note"):
            entries.append({"kind": "reading", "about": [key_of(entry)],
                            "author": f"note in {path.name}", "date": entry["date"][:10],
                            "text": p["note"]})
    if entries:
        append(ledger_path(factory), entries)
    return entries


# ------------------------------------------------------------------- compare

def versions(entries: list[dict]) -> list[dict]:
    """Every version key in the ledger, in the order it first appears."""
    out: dict[str, dict] = {}
    for e in entries:
        if e.get("kind") not in ("pass", "calibration"):
            continue
        v = out.setdefault(key_of(e), {
            "version": key_of(e), "factory_version": e["version"], "state": e.get("state"),
            "passes": [], "calibrations": [], "first_date": e.get("date"), "last_date": e.get("date"),
            "models": [], "sources": [], "version_notes": []})
        v["passes" if e["kind"] == "pass" else "calibrations"].append(e["id"])
        v["last_date"] = e.get("date")
        for field, val in (("models", e.get("model")), ("sources", e.get("source")),
                           ("version_notes", e.get("version_note"))):
            if val and val not in v[field]:
                v[field].append(val)
    return list(out.values())


def select(all_versions: list[dict], wanted: list[str]) -> list[dict]:
    """The versions named, in ledger order.

    A name is a version key or the start of one (a commit prefix picks every
    state on that commit), or the start of a pass id, such as its timestamp.
    """
    return pick(all_versions, wanted, lambda v: v["passes"] + v["calibrations"])


def group_numbers(runs: list[dict], pass_mark, bare: list[dict] | None, src: str) -> dict:
    judged = [r for r in runs if r["pass"] is not None]
    passing = [r for r in judged if r["pass"]]
    n_all, n_j, n_p = len(runs), len(judged), len(passing)
    rate = n_p / n_j if n_j else None
    voids = [r.get("void") for r in runs]
    costs = [r.get("cost_usd") for r in runs]
    pcosts = [r.get("cost_usd") for r in passing]
    secs = [r.get("seconds") for r in runs]
    turns = [r.get("turns") for r in runs]
    pturns = [r.get("turns") for r in passing]
    known = lambda xs: sum(x is not None for x in xs)  # noqa: E731
    nums = {
        "runs": cell(n_j, n_all, src),
        "passed": cell(n_p, n_j, src),
        "pass_rate": cell(rate, n_j, src),
        "void": cell(None if None in voids else sum(bool(v) for v in voids), n_all, src),
        "crashed": cell(sum(bool(r.get("crashed")) for r in runs), n_all, src),
        "pass_mark": cell(pass_mark, n_all, src),
        "cost_per_run_usd": cell(mean(costs), known(costs), src),
        "cost_per_passing_run_usd": cell(mean(pcosts), known(pcosts), src),
        "seconds_per_run": cell(mean(secs), known(secs), src, 1),
        "turns_per_run": cell(mean(turns), known(turns), src, 1),
        "turns_per_passing_run": cell(mean(pturns), known(pturns), src, 1),
    }
    if bare is not None:
        bj = [r for r in bare if r["pass"] is not None]
        lift = rate - sum(bool(r["pass"]) for r in bj) / len(bj) if bj and rate is not None else None
        nums["lift_over_bare"] = cell(lift, n_j + len(bj), src)
    with_skills = [r for r in runs if r.get("skills") is not None]
    for skill in sorted({s for r in with_skills for s in r["skills"]}):
        nums[SKILL_METRIC + skill] = cell(
            sum(skill in r["skills"] for r in with_skills), len(with_skills), src)
    return nums


def numbers_of(entries: list[dict], key: str) -> dict[str, dict]:
    """Group name -> metric -> cell, for one version key."""
    passes = [e for e in entries if e.get("kind") == "pass" and key_of(e) == key]
    cals = [e for e in entries if e.get("kind") == "calibration" and key_of(e) == key]
    runs: dict[tuple, list] = {}
    marks: dict[tuple, object] = {}
    ids: dict[tuple, list] = {}
    for p in passes:
        for r in p["runs"]:
            g = (r["scenario"], r["arm"])
            runs.setdefault(g, []).append(r)
            ids.setdefault(g, [])
            if p["id"] not in ids[g]:
                ids[g].append(p["id"])
            marks[g] = p.get("pass_marks", {}).get(f"{g[0]} {g[1]}", marks.get(g))
    out = {}
    for g, rs in runs.items():
        froms = sorted({p["source"] for p in passes if p["id"] in ids[g]})
        src = f"{'; '.join(froms)}: pass {', '.join(ids[g])}"
        bare = runs.get((g[0], "bare")) if g[1] != "bare" else None
        nums = group_numbers(rs, marks.get(g), bare, src)
        if g[1] != "bare" and "lift_over_bare" not in nums:
            nums["lift_over_bare"] = cell(None, len(rs), src)
        out[f"{g[0]} {g[1]}"] = nums
    for c in cals:  # the latest check of each judge in this version
        for sid, j in c["judges"].items():
            src = f"{c['source']}: {c['id']}"
            out[f"{sid} judge"] = {"judge_samples": cell(j["samples"], j["samples"], src),
                                   "judge_agreed": cell(j["agreed"], j["samples"], src)}
    return out


def definition(metric: str) -> str:
    if metric.startswith(SKILL_METRIC):
        return SKILL_DEFINITION.format(skill=metric[len(SKILL_METRIC):])
    return DEFINITIONS[metric]


def compare(entries: list[dict], wanted: list[str] | None = None) -> dict:
    """Each chosen version's numbers next to the others', with the changes between them."""
    chosen = select(versions(entries), wanted or [])
    keys = [v["version"] for v in chosen]
    nums = {k: numbers_of(entries, k) for k in keys}
    rows = compare_rows(keys, nums, definition, list(DEFINITIONS), ABSENT)
    return {
        "about": ("The factory's eval numbers per version, in the order the ledger recorded them. "
                  "Each change is the difference from the last earlier version that ran the same "
                  "scenario and arm. No number here is a score or a verdict, and versions are "
                  "not ranked: what the numbers mean is for readers to write down as readings."),
        "ledger": LEDGER,
        "versions": chosen,
        "rows": rows,
        "readings": readings_about(entries, keys),
    }


# ---------------------------------------------------------------------- page

def short(key: str) -> str:
    version, _, state = key.partition("+")
    sha, dash, rest = version.partition("-")
    return sha[:7] + (f"-{rest}" if dash else "") + (f"+{state}" if state else "")


def render(data: dict) -> str:
    e = html.escape
    vs = data["versions"]
    all_notes = list(dict.fromkeys(n for v in vs for n in v["version_notes"]))

    def version_cells(v: dict) -> list[str]:
        notes = "".join(f'<span class="sub">version {"*" * (all_notes.index(n) + 1)}</span>'
                        for n in v["version_notes"])
        models = f'<span class="sub">model: {e(", ".join(v["models"]))}</span>' if v["models"] else ""
        return [e(str(v["first_date"] or "")), e(", ".join(v["passes"] + v["calibrations"])),
                e(", ".join(v["sources"])) + models + notes]

    return render_page({
        "title": f"The factory's eval numbers for {len(vs)} versions, side by side",
        "author": "tools/metrics.py", "absent": ABSENT,
        "takeaway": ("Each version's numbers sit next to the last earlier version that ran the "
                     "same scenario and arm, with the change between them. A change is a difference, "
                     "not a verdict: what the numbers mean is for you to say, and the readings people "
                     "and agents wrote are at the end."),
        "versions_intro": ("In the order the ledger recorded them. A <code>-modified</code> version had "
                           "uncommitted changes; the part after <code>+</code> tells uncommitted states apart."),
        "version_headers": ["Date", "Passes", "Source"], "version_cells": version_cells,
        "version_notes": all_notes, "short": short,
        "numbers_heading": "Numbers, by scenario and arm",
        "numbers_intro": ("Every number for every version shown. Columns are the versions that ran each "
                          "scenario and arm; <i>n</i> is how many runs a number rests on. Definitions and "
                          "sources are under each table."),
        "add_reading": "python3 tools/metrics.py add-reading --about VERSION --author WHO --text TEXT",
        "json_command": "python3 tools/metrics.py compare",
    }, data)


# ----------------------------------------------------------------------- cli

def main(argv: list[str], factory: Path = FACTORY) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("versions", help="list the versions in the ledger, as JSON")
    c = sub.add_parser("compare", help="versions side by side, as JSON")
    c.add_argument("version", nargs="*", help="version keys, prefixes or pass ids (default: all)")
    c.add_argument("--html", nargs="?", const=DEFAULT_PAGE, metavar="PATH",
                   help=f"also write the page (default {DEFAULT_PAGE})")
    r = sub.add_parser("add-reading", help="append a reading about one or more versions")
    r.add_argument("--about", nargs="+", required=True, metavar="VERSION")
    r.add_argument("--author", required=True, help="who wrote it: a role or an agent, not contact details")
    r.add_argument("--text", required=True)
    i = sub.add_parser("import-results", help="import a hand-picked results file")
    i.add_argument("file", type=Path)
    args = ap.parse_args(argv)

    path = ledger_path(factory)
    try:
        if args.command == "import-results":
            added = import_results(args.file, factory)
            print(f"imported {sum(e['kind'] == 'pass' for e in added)} passes and "
                  f"{sum(e['kind'] == 'reading' for e in added)} readings into {LEDGER}")
            return 0
        entries = read(path)
        if args.command == "versions":
            print(json.dumps(versions(entries), indent=1))
        elif args.command == "compare":
            data = compare(entries, args.version)
            if args.html:
                page = factory / args.html
                if not inside(page, factory):
                    raise ValueError(f"the page must go inside the repository: {args.html}")
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text(render(data))
                print(f"page: {args.html}", file=sys.stderr)
            print(json.dumps(data, indent=1))
        elif args.command == "add-reading":
            about = [v["version"] for v in select(versions(entries), args.about)]
            entry = reading(about, args.author, args.text)
            append(path, [entry])
            print(json.dumps(entry, indent=1))
    except ValueError as err:
        print(f"metrics: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
