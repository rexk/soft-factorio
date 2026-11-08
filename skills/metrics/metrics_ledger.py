"""The ledger idea both metrics tools share: append-only JSON lines, numbers
side by side with the change between them, and the page that shows them.

Used by metrics.py in this folder (a repository's own numbers) and by the
factory's tools/metrics.py (its eval numbers). Python 3, standard library
only. Nothing here sends anything anywhere.
"""

from __future__ import annotations

import datetime
import html
import json
import os
import re
from pathlib import Path

try:
    import fcntl
except ImportError:  # not on Windows; appends there are single writes only
    fcntl = None

MAX_READING = 1000  # readings are short notes, not transcripts


# ------------------------------------------------------------------ the ledger

def append(path: Path, entries: list[dict]) -> None:
    """Append entries as JSON lines in one locked write, so parallel writers don't interleave."""
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


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")


def reading(about: list[str], author: str, text: str, **extra) -> dict:
    """A reading entry, checked: someone wrote it, and it is a short note."""
    text, author = text.strip(), author.strip()
    if not text or not author:
        raise ValueError("a reading needs an author and some text")
    if len(text) > MAX_READING:
        raise ValueError(f"a reading is a short note: {len(text)} characters, "
                         f"keep it under {MAX_READING}")
    return {"kind": "reading", "about": about, "author": author, "date": now(), "text": text, **extra}


def readings_about(entries: list[dict], keys: list[str]) -> list[dict]:
    """The readings that name any of these versions, oldest first, never grouped by author."""
    return [{k: r.get(k) for k in ("date", "author", "about", "text")}
            for r in entries if r.get("kind") == "reading" and set(r.get("about", [])) & set(keys)]


# ------------------------------------------------------------------ numbers

def natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def median(xs: list) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    return float(xs[mid]) if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def cell(value, count: int, source: str, digits: int = 3) -> dict:
    """One number: its value (None when missing, never 0), how many it rests on, where it came from."""
    if value is None:
        return {"value": None, "missing": True, "count": count, "source": source}
    if isinstance(value, float):
        value = round(value, digits)
    return {"value": value, "missing": False, "count": count, "source": source}


def compare_rows(keys: list[str], nums: dict[str, dict[str, dict]], definition, order: list[str],
                 absent: str, group_order: list[str] | None = None) -> list[dict]:
    """One row per group and number, with a cell for every version in `keys`.

    `nums` is version -> group -> metric -> cell. Each cell's change is the
    difference from the last earlier version that had the same group, and
    only when both values are there: a missing value never compares as 0.
    """
    present = {g for k in keys for g in nums[k]}
    if group_order:
        groups = [g for g in group_order if g in present] + sorted(present - set(group_order), key=natural)
    else:
        groups = sorted(present, key=natural)
    rows = []
    for g in groups:
        metrics = sorted({m for k in keys for m in nums[k].get(g, {})},
                         key=lambda m: (order.index(m) if m in order else len(order), m))
        for m in metrics:
            cells, prev = [], None  # prev: the last earlier version that had this group
            for k in keys:
                if g not in nums[k]:
                    c = {"value": None, "missing": True, "count": 0, "source": absent}
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
    return rows


def select(all_versions: list[dict], wanted: list[str], also=lambda v: []) -> list[dict]:
    """The versions named, in their own order.

    A name is a version key or the start of one, or the start of any of
    `also(version)`, such as a pass id.
    """
    if not wanted:
        return all_versions
    picked = []
    for w in wanted:
        hits = [v for v in all_versions
                if v["version"].startswith(w) or any(i.startswith(w) for i in also(v))]
        if not hits:
            raise ValueError(f"no version matches {w!r}")
        picked += [v for v in hits if v not in picked]
    return [v for v in all_versions if v in picked]


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


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


def render(page: dict, data: dict) -> str:
    """The comparison as a page: every version, every number, the readings.

    `page` holds the words around the data: title, author, takeaway,
    versions_intro and numbers_intro (trusted HTML written by the tool),
    version_headers and version_cells(version) -> escaped HTML cells after
    the ID and version, short(key) for column heads, version_notes (text),
    add_reading and json_command (shell commands).
    """
    e = html.escape
    vs = data["versions"]
    label = {v["version"]: f"V{i}" for i, v in enumerate(vs, 1)}
    today = datetime.date.today().isoformat()
    title = html.escape(page["title"], quote=False)
    parts = [
        "<!doctype html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title}</title>",
        f"<style>{PAGE_STYLE}</style>", "</head>", "<body>", "<main>", "<header>",
        f"<h1>{title}</h1>",
        f'<div class="meta"><span>Date: <time datetime="{today}">{today}</time></span>'
        f"<span>Author: {e(page['author'])}</span><span>Source: <code>{e(data['ledger'])}</code></span></div>",
        "</header>",
        f'<p class="takeaway">{page["takeaway"]}</p>',
        '<section id="versions"><h2>Versions</h2>',
        f"<p>{page['versions_intro']}</p>",
        '<div class="scroll"><table><thead><tr><th>ID</th><th>Version</th>'
        + "".join(f"<th>{e(h)}</th>" for h in page["version_headers"]) + "</tr></thead><tbody>",
    ]
    for v in vs:
        parts.append(f'<tr id="{label[v["version"]].lower()}"><td><b>{label[v["version"]]}</b></td>'
                     f'<td><code>{e(v["version"])}</code></td>'
                     + "".join(f"<td>{c}</td>" for c in page["version_cells"](v)) + "</tr>")
    parts.append("</tbody></table></div>")
    parts += [f'<p class="sub">{"*" * i} Version {e(n)}.</p>'
              for i, n in enumerate(page.get("version_notes", []), 1)]
    parts.append("</section>")

    groups: dict[str, list] = {}
    for row in data["rows"]:
        groups.setdefault(row["group"], []).append(row)
    parts.append(f'<section id="numbers"><h2>{e(page["numbers_heading"])}</h2>'
                 f"<p>{page['numbers_intro']}</p></section>")
    for g, rows in groups.items():
        cols = [c["version"] for c in rows[0]["cells"] if c["source"] != page["absent"]]
        gid = "g-" + re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-")
        parts.append(f'<section id="{gid}"><h2>{e(g)}</h2><div class="scroll"><table><thead><tr><th>Number</th>')
        parts += [f'<th><a href="#{label[k].lower()}">{label[k]}</a>'
                  f'<span class="sub">{e(page["short"](k))}</span></th>' for k in cols]
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
    parts.append(f"<p>Add one with <code>{e(page['add_reading'])}</code>.</p></section>")
    parts.append(f"<footer>Composed {today} by {e(page['author'])} from {e(data['ledger'])}. "
                 f"The same comparison as JSON: <code>{e(page['json_command'])}</code>.</footer>")
    parts += ["</main>", "</body>", "</html>", ""]
    return "\n".join(parts)
