#!/usr/bin/env python3
"""Show that nothing private is in the repository (B12).

    python3 tools/privacy_scan.py [repo]

Scans every file git would commit (tracked, plus untracked files that aren't
ignored) and every commit message for:

  - email addresses, except reserved and no-reply domains
  - phone numbers
  - home-directory paths (/home/<name>, /Users/<name>, C:\\Users\\<name>)
  - private terms, read from `.privacy-terms` in the repo (one per line,
    gitignored) and from the PRIVACY_TERMS environment variable (newline
    separated, e.g. a CI secret)

A private term found is reported by its number, never its text, so the
report is safe to print in a public CI log. Exits 1 if anything is found.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
SAFE_EMAIL_DOMAINS = re.compile(
    r"(^|\.)(example\.(com|org|net)|invalid|test|localhost|users\.noreply\.github\.com)$"
    r"|^(anthropic\.com)$",
    re.I,
)
SAFE_EMAIL_USERS = {"noreply", "no-reply"}
PHONE = re.compile(r"(?<![\w.])(\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w.])")
HOME = re.compile(r"(/home/|/Users/|[A-Za-z]:\\Users\\)(?!<|\{|\$|user\b|you\b|name\b)[A-Za-z0-9._-]+")


@dataclass
class Finding:
    where: str  # path:line, or commit:<sha>
    kind: str
    text: str  # what matched; for private terms, only the term's number

    def __str__(self) -> str:
        return f"{self.where}: {self.kind}: {self.text}"


def private_terms(repo: Path) -> list[str]:
    raw = os.environ.get("PRIVACY_TERMS", "")
    f = repo / ".privacy-terms"
    if f.exists():
        raw += "\n" + f.read_text()
    terms = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line.lower() not in (t.lower() for t in terms):
            terms.append(line)
    return terms


def scan_text(text: str, where: str, terms: list[str]) -> list[Finding]:
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        at = f"{where}:{n}"
        for m in EMAIL.finditer(line):
            user = m.group(0).split("@")[0].lower()
            if user not in SAFE_EMAIL_USERS and not SAFE_EMAIL_DOMAINS.search(m.group(1)):
                found.append(Finding(at, "email", m.group(0)))
        for m in PHONE.finditer(line):
            found.append(Finding(at, "phone", m.group(0)))
        for m in HOME.finditer(line):
            found.append(Finding(at, "home path", m.group(0)))
        lower = line.lower()
        for i, term in enumerate(terms, 1):
            if re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", lower):
                found.append(Finding(at, "private term", f"#{i}"))
    return found


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout


def files(repo: Path) -> list[str]:
    out = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return sorted({p for p in out.split("\0") if p and (repo / p).is_file()} - {".privacy-terms"})


def commit_messages(repo: Path) -> list[tuple[str, str]]:
    if subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=repo,
                      capture_output=True).returncode != 0:
        return []
    out = git(repo, "log", "--all", "--format=%H%x00%B%x01")
    msgs = []
    for entry in out.split("\x01"):
        if "\x00" in entry:
            sha, body = entry.strip("\n").split("\x00", 1)
            msgs.append((sha[:12], body))
    return msgs


def scan(repo: Path) -> list[Finding]:
    terms = private_terms(repo)
    found: list[Finding] = []
    for path in files(repo):
        try:
            text = (repo / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary files hold no text to leak through this scan
        found += scan_text(text, path, terms)
        found += scan_text(path, f"{path} (file name)", terms)
    for sha, body in commit_messages(repo):
        found += scan_text(body, f"commit {sha}", terms)
    return found


def main(argv: list[str]) -> int:
    repo = Path(argv[1] if len(argv) > 1 else ".").resolve()
    found = scan(repo)
    terms = len(private_terms(repo))
    for f in found:
        print(f)
    note = f"{terms} private terms" if terms else "no private terms configured"
    print(f"privacy scan: {len(found)} finding(s) in {len(files(repo))} files ({note})")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
