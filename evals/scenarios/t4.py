"""T4 Same in every tool (B4).

T1 (apply from START.md, then a vague ask) run with Codex instead of Claude
Code, judged by the same code checks and the same calibrated judge. Pass per
run when T1 passes under Codex; the behaviour holds when Codex's pass rate
matches Claude Code's.

Arms: `preinstalled` tests whether Codex finds and follows the installed
skills (B4 itself); `apply` also has Codex apply the factory, which its
sandbox blocks headless: it mounts `.agents/` and `.git` read-only, and with
no person to approve a write the helper fails.

Not covered yet:
- T3 under Codex: its sandbox makes .git read-only, so it can't commit,
  push or open the pull requests T3 judges. Running it needs Codex without
  its sandbox, which is the maintainer's call.
- Cursor: no headless runner on the eval machine; checked by hand.
"""

from __future__ import annotations

from pathlib import Path

import lib
from scenarios import t1

ID = "T4"
BEHAVIOURS = ["B4"]
PASS_RATE = 0.8


def run(dest: Path, arm: str, logdir: Path, model: str) -> dict:
    lib.use_tool("codex")
    try:
        result = t1.run(dest, arm, logdir, model)
    finally:
        lib.use_tool("claude")
    result.update(tool="codex", scenario_run="T1")
    return result
