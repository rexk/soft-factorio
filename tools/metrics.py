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
import datetime
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import fcntl
except ImportError:  # not on Windows; appends there are single writes only
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factory import LEDGER, NOT_FACTORY_TEXT, factory_version, git_out  # noqa: E402

FACTORY = Path(__file__).resolve().parent.parent
DEFAULT_PAGE = ".scratch/metrics/compare.html"
MAX_READING = 1000  # readings are short notes, not transcripts

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


def append(path: Path, entries: list[dict]) -> None:
    """Append entries as JSON lines in one locked write, so parallel passes don't interleave."""
    data = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if fcntl:
            fcntl.flock(fd, fcntl.LOCK_EX)
        while data:
            data = data[os.write(fd, data):]
    finally:
        os.close(fd)  # closing releases the lock


def read(path: Path) -> list[dict]:
    """Every entry, in the order written; exact duplicates (as a union merge can leave) once."""
    if not path.exists():
        return []
    seen, entries = set(), []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line in seen:
            continue
        seen.add(line)
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path.name}:{n}: not a JSON line ({e.msg})") from None
    return entries


def key_of(entry: dict) -> str:
    return entry["version"] + (f"+{entry['state']}" if entry.get("state") else "")


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")


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

def natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def cell(value, count: int, source: str, digits: int = 3) -> dict:
    if value is None:
        return {"value": None, "missing": True, "count": count, "source": source}
    if isinstance(value, float):
        value = round(value, digits)
    return {"value": value, "missing": False, "count": count, "source": source}


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
    if not wanted:
        return all_versions
    picked = []
    for w in wanted:
        hits = [v for v in all_versions
                if v["version"].startswith(w)
                or any(i.startswith(w) for i in v["passes"] + v["calibrations"])]
        if not hits:
            raise ValueError(f"no version in the ledger matches {w!r}")
        picked += [v for v in hits if v not in picked]
    return [v for v in all_versions if v in picked]


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
    groups = sorted({g for k in keys for g in nums[k]}, key=natural)
    order = list(DEFINITIONS)
    rows = []
    for g in groups:
        metrics = sorted({m for k in keys for m in nums[k].get(g, {})},
                         key=lambda m: (order.index(m) if m in order else len(order), m))
        for m in metrics:
            cells, prev = [], None  # prev: the last earlier version that ran this group
            for k in keys:
                if g not in nums[k]:
                    c = {"value": None, "missing": True, "count": 0, "source": ABSENT}
                    c.update(version=k, change=None, change_from=None)
                    cells.append(c)
                    continue
                c = dict(nums[k][g].get(m) or cell(None, 0, "not recorded in this version"))
                p = nums[prev][g].get(m) if prev else None
                change = None
                if p and not p["missing"] and not c["missing"] \
                        and not isinstance(c["value"], bool) and isinstance(c["value"], (int, float)):
                    change = round(c["value"] - p["value"], 3)
                c.update(version=k, change=change, change_from=prev)
                cells.append(c)
                prev = k
            rows.append({"group": g, "metric": m, "definition": definition(m), "cells": cells})
    readings = [e for e in entries if e.get("kind") == "reading" and set(e.get("about", [])) & set(keys)]
    return {
        "about": ("The factory's eval numbers per version, in the order the ledger recorded them. "
                  "Each change is the difference from the last earlier version that ran the same "
                  "scenario and arm. No number here is a score or a verdict, and versions are "
                  "not ranked: what the numbers mean is for readers to write down as readings."),
        "ledger": LEDGER,
        "versions": chosen,
        "rows": rows,
        "readings": [{k: r.get(k) for k in ("date", "author", "about", "text")} for r in readings],
    }


# ---------------------------------------------------------------------- page

PAGE_STYLE = """
:root{--bg:#f4f5f7;--surface:#ffffff;--fg:#1a1f27;--muted:#5d6672;--line:#d6dae0;
--accent:#2f5fd0;--accent-soft:#e6ecfb;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:ui-monospace,Menlo,Consolas,monospace;color-scheme:light}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#12161b;--surface:#1b2027;
--fg:#e6e9ed;--muted:#9aa3ae;--line:#2e3540;--accent:#7ea2ff;--accent-soft:#1f2a44;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#12161b;--surface:#1b2027;--fg:#e6e9ed;--muted:#9aa3ae;--line:#2e3540;
--accent:#7ea2ff;--accent-soft:#1f2a44;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 var(--sans)}
main{max-width:960px;margin:0 auto;padding:24px 16px 48px;display:flex;flex-direction:column;gap:28px}
h1{font-size:1.6rem;line-height:1.2;margin:0;text-wrap:balance}
h2{font-size:1.15rem;margin:0 0 8px}
p{margin:0 0 8px}
ul{margin:0;padding-left:1.2em} li{margin:0 0 6px}
code{font:.88em var(--mono)}
a{color:var(--accent)}
.meta{font:13px/1.4 var(--mono);color:var(--muted);display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:8px}
.takeaway{background:var(--accent-soft);border-left:4px solid var(--accent);padding:12px 14px;border-radius:0 6px 6px 0;font-weight:600}
.scroll{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.8rem}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.metric{white-space:nowrap}
.sub{display:block;color:var(--muted);font-size:.78rem;font-weight:400}
.missing{color:var(--muted);font-style:italic}
details{margin-top:6px} summary{cursor:pointer}
summary:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
footer{font:12px/1.4 var(--mono);color:var(--muted);border-top:1px solid var(--line);padding-top:10px}
"""


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".") if v % 1 else f"{v:.0f}"
    return str(v)


def short(key: str) -> str:
    version, _, state = key.partition("+")
    sha, dash, rest = version.partition("-")
    return sha[:7] + (f"-{rest}" if dash else "") + (f"+{state}" if state else "")


def render(data: dict) -> str:
    e = html.escape
    vs = data["versions"]
    label = {v["version"]: f"V{i}" for i, v in enumerate(vs, 1)}
    today = datetime.date.today().isoformat()
    parts = [
        "<!doctype html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>The factory's eval numbers for {len(vs)} versions, side by side</title>",
        f"<style>{PAGE_STYLE}</style>", "</head>", "<body>", "<main>", "<header>",
        f"<h1>The factory's eval numbers for {len(vs)} versions, side by side</h1>",
        f'<div class="meta"><span>Date: <time datetime="{today}">{today}</time></span>'
        f"<span>Author: tools/metrics.py</span><span>Source: <code>{e(data['ledger'])}</code></span></div>",
        "</header>",
        '<p class="takeaway">Each version\'s numbers sit next to the last earlier version that ran the '
        "same scenario and arm, with the change between them. A change is a difference, not a verdict: "
        "what the numbers mean is for you to say, and the readings people and agents wrote are at the end.</p>",
        '<section id="versions"><h2>Versions</h2>',
        "<p>In the order the ledger recorded them. A <code>-modified</code> version had uncommitted "
        "changes; the part after <code>+</code> tells uncommitted states apart.</p>",
        '<div class="scroll"><table><thead><tr><th>ID</th><th>Version</th><th>Date</th>'
        "<th>Passes</th><th>Source</th></tr></thead><tbody>",
    ]
    all_notes = list(dict.fromkeys(n for v in vs for n in v["version_notes"]))
    for v in vs:
        notes = "".join(f'<span class="sub">version {"*" * (all_notes.index(n) + 1)}</span>'
                        for n in v["version_notes"])
        models = f'<span class="sub">model: {e(", ".join(v["models"]))}</span>' if v["models"] else ""
        runs = ", ".join(v["passes"] + v["calibrations"])
        parts.append(
            f'<tr id="{label[v["version"]].lower()}"><td><b>{label[v["version"]]}</b></td>'
            f'<td><code>{e(v["version"])}</code></td><td>{e(str(v["first_date"] or ""))}</td>'
            f"<td>{e(runs)}</td><td>{e(', '.join(v['sources']))}{models}{notes}</td></tr>")
    parts.append("</tbody></table></div>")
    parts += [f'<p class="sub">{"*" * i} Version {e(n)}.</p>' for i, n in enumerate(all_notes, 1)]
    parts.append("</section>")

    groups: dict[str, list] = {}
    for row in data["rows"]:
        groups.setdefault(row["group"], []).append(row)
    parts.append('<section id="numbers"><h2>Numbers, by scenario and arm</h2>'
                 "<p>Every number for every version shown. Columns are the versions that ran each "
                 "scenario and arm; <i>n</i> is how many runs a number rests on. Definitions and "
                 "sources are under each table.</p></section>")
    for g, rows in groups.items():
        cols = [c["version"] for c in rows[0]["cells"] if c["source"] != ABSENT]
        gid = "g-" + re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-")
        parts.append(f'<section id="{gid}"><h2>{e(g)}</h2><div class="scroll"><table><thead><tr><th>Number</th>')
        parts += [f'<th><a href="#{label[k].lower()}">{label[k]}</a><span class="sub">{e(short(k))}</span></th>'
                  for k in cols]
        parts.append("</tr></thead><tbody>")
        for r in rows:
            by = {c["version"]: c for c in r["cells"]}
            parts.append(f'<tr><td class="metric">{e(r["metric"])}</td>')
            for k in cols:
                c = by[k]
                if c["missing"]:
                    parts.append(f'<td class="num"><span class="missing">missing</span>'
                                 f'<span class="sub">n={c["count"]}</span></td>')
                    continue
                ch = ""
                if c["change"] is not None:
                    sign = "+" if c["change"] > 0 else ""
                    ch = f'<span class="sub">{sign}{fmt(c["change"])} from {label[c["change_from"]]}</span>'
                parts.append(f'<td class="num">{e(fmt(c["value"]))}<span class="sub">n={c["count"]}</span>{ch}</td>')
            parts.append("</tr>")
        parts.append("</tbody></table></div><details><summary>Definitions and sources</summary><ul>")
        for r in rows:
            parts.append(f"<li><b>{e(r['metric'])}</b>: {e(r['definition'])}</li>")
        srcs = sorted({c["source"] for r in rows for c in r["cells"] if c["version"] in cols})
        parts += [f'<li class="sub">Source: {e(s)}</li>' for s in srcs]
        parts.append("</ul></details></section>")

    parts.append('<section id="readings"><h2>Readings</h2>')
    if data["readings"]:
        parts.append("<p>What people and agents wrote about these versions, oldest first. "
                     "A new reading never replaces an earlier one.</p><ul>")
        for r in data["readings"]:
            about = ", ".join(label.get(a, a) for a in r["about"])
            parts.append(f'<li><span class="sub">{e(str(r["date"]))} · {e(str(r["author"]))} · '
                         f"about {e(about)}</span>{e(str(r['text']))}</li>")
        parts.append("</ul>")
    else:
        parts.append("<p>No readings yet about these versions.</p>")
    parts.append("<p>Add one with <code>python3 tools/metrics.py add-reading --about VERSION "
                 "--author WHO --text TEXT</code>.</p></section>")
    parts.append(f"<footer>Composed {today} by tools/metrics.py from {e(data['ledger'])}. "
                 "The same comparison as JSON: <code>python3 tools/metrics.py compare</code>.</footer>")
    parts += ["</main>", "</body>", "</html>", ""]
    return "\n".join(parts)


# ----------------------------------------------------------------------- cli

def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


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
            text = args.text.strip()
            if not text or not args.author.strip():
                raise ValueError("a reading needs an author and some text")
            if len(text) > MAX_READING:
                raise ValueError(f"a reading is a short note: {len(text)} characters, "
                                 f"keep it under {MAX_READING}")
            about = [v["version"] for v in select(versions(entries), args.about)]
            entry = {"kind": "reading", "about": about, "author": args.author.strip(),
                     "date": now(), "text": text}
            append(path, [entry])
            print(json.dumps(entry, indent=1))
    except ValueError as err:
        print(f"metrics: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
