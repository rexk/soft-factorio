#!/usr/bin/env python3
"""The one check command, the same locally and in CI.

    python3 tools/check.py

Runs the unit tests under tests/, then the privacy scan. Scenario evals are
not part of it: they run agent sessions and cost API usage (see evals/run.py).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

steps = [
    ("unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
    ("privacy scan", [sys.executable, "tools/privacy_scan.py", "."]),
]

failed = []
for name, cmd in steps:
    print(f"== {name}", flush=True)
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        failed.append(name)

print("\n" + ("FAILED: " + ", ".join(failed) if failed else "All checks passed."))
sys.exit(1 if failed else 0)
