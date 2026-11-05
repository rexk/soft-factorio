"""T6 Report on a repo (B7).

typewirets with the factory installed. The person asks "What state is this
repo in?" Pass when the agent produced an HTML page that parses and makes no
outside requests (code), and a judge model, calibrated on
evals/calibration/t6/, finds its takeaway comes first and no section is a
wall of text.

Not yet checked: rendering at 400px in both themes. That needs a headless
browser, which the eval machine doesn't have yet.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import lib

ID = "T6"
BEHAVIOURS = ["B7"]
REPO = "typewirets"
PASS_RATE = 0.8
TASK = "What state is this repo in?"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}
OPTIONAL_END = {"p", "li", "td", "th", "tr", "thead", "tbody", "tfoot", "option",
                "dt", "dd", "colgroup", "caption", "html", "head", "body"}
REQUEST = re.compile(
    r"""<(?:script|img|iframe|link|source|video|audio|embed|object)\b[^>]*\b(?:src|href|data)\s*=\s*["']?\s*(?:https?:)?//"""
    r"""|url\(\s*["']?\s*(?:https?:)?//|@import\s+["']?(?:https?:)?//""", re.I)


class Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                left = self.stack.pop()
                if left not in OPTIONAL_END:
                    self.errors.append(f"<{left}> not closed before </{tag}>")
            self.stack.pop()
        else:
            self.errors.append(f"stray </{tag}>")


def parses(page: str) -> list[str]:
    b = Balance()
    b.feed(page)
    b.close()
    return b.errors + [f"<{t}> never closed" for t in b.stack if t not in OPTIONAL_END]


RUBRIC = """You judge an HTML page a coding agent wrote to answer a person's question
"What state is this repo in?". The page is meant to be read on a phone.

Decide:
- takeaway_first: true if the first thing after the title is a short statement
  of the overall answer (the repo's state in a sentence or two), before any
  detail.
- wall_of_text: true if any section is mainly long paragraphs (more than about
  three lines on a phone, roughly 45 words) instead of opening with a table,
  list or diagram.
- answers_question: true if the page actually says what state the repo is in.
- reason: one sentence.

JSON keys: takeaway_first, wall_of_text, answers_question, reason."""


def judge_page(page: str) -> dict:
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", page, flags=re.S | re.I)
    return lib.model_judge(RUBRIC, text[:60000])


def accepts(v: dict) -> bool:
    return (v.get("takeaway_first") is True and v.get("wall_of_text") is False
            and v.get("answers_question") is True)


def judge_accepts(sample: str) -> bool:
    return not parses(sample) and not REQUEST.search(sample) and accepts(judge_page(sample))


def pages_written(repo: Path, log: Path) -> dict[str, str]:
    pages = {}
    for call in lib.tool_inputs(log, ("Write", "Edit", "MultiEdit")):
        path = call.get("file_path", "")
        if path.endswith((".html", ".htm")):
            p = Path(path) if Path(path).is_absolute() else repo / path
            if p.exists():
                pages[str(p)] = p.read_text()
            elif "content" in call:
                pages[str(p)] = call["content"]
    return pages


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    repo = lib.snapshot(REPO, dest)
    lib.preinstall_factory(repo)
    lib.commit_all(repo, "Apply software factory (preinstalled by eval)")
    agent = lib.run_agent(repo, TASK, logdir / "task.jsonl", model)
    pages = pages_written(repo, logdir / "task.jsonl")
    checks = {}
    for path, page in pages.items():
        (logdir / Path(path).name).write_text(page)
        checks[path] = {"parse_errors": parses(page)[:10],
                        "outside_requests": [m.group(0)[:80] for m in REQUEST.finditer(page)][:5],
                        "judge": judge_page(page)}
    good = [p for p, c in checks.items()
            if not c["parse_errors"] and not c["outside_requests"] and accepts(c["judge"])]
    return {
        "pass": bool(good),
        "pages": checks,
        "skills_used": agent.skills_used,
        "cost_usd": round(agent.cost_usd, 3),
        "agent_error": agent.is_error,
        "final_reply": agent.result[:1500],
    }
