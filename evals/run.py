#!/usr/bin/env python3
"""Run scenario evals and report a pass rate per scenario and arm.

    python3 evals/run.py T1 --arms preinstalled,bare --runs 3
    python3 evals/run.py T1 --calibrate

--calibrate checks each scenario's judge against the known-good and known-bad
samples in evals/calibration/<id>/ instead of running agents; a judge that
disagrees with any sample isn't trusted.

Each run gets its own snapshot of the scenario's repository in a scratch
folder (FACTORY_EVAL_DIR, default: the system temp dir). Results land in
<scratch>/results/<timestamp>/ as one JSON per run plus summary.json.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def load(scenario_id: str):
    return importlib.import_module(f"scenarios.{scenario_id.lower()}")


def calibrate(scenario_ids: list[str]) -> int:
    root = Path(__file__).resolve().parent / "calibration"
    wrong = 0
    for sid in scenario_ids:
        mod = load(sid)
        for want, folder in ((True, "good"), (False, "bad")):
            for sample in sorted((root / sid.lower() / folder).glob("*")):
                got = mod.judge_accepts(sample.read_text())
                ok = got == want
                wrong += not ok
                print(f"{sid} {folder}/{sample.name}: judge {'accepts' if got else 'rejects'}"
                      f" {'ok' if ok else 'WRONG'}", flush=True)
    print("calibrated" if not wrong else f"{wrong} sample(s) judged wrong: fix the judge first")
    return 1 if wrong else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios", nargs="+", help="scenario ids, e.g. T1 T3")
    ap.add_argument("--arms", default="preinstalled", help="comma-separated arms")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="opus", help="model for the agent under test")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--calibrate", action="store_true", help="check judges against samples")
    args = ap.parse_args()
    if args.calibrate:
        return calibrate(args.scenarios)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = lib.workdir() / "results" / stamp
    jobs = []
    for sid in args.scenarios:
        mod = load(sid)
        for arm in args.arms.split(","):
            for i in range(1, args.runs + 1):
                jobs.append((sid, mod, arm, i))

    def one(job):
        sid, mod, arm, i = job
        name = f"{sid}-{arm}-{i}"
        logdir = out / name
        logdir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        try:
            res = mod.run(lib.workdir() / "runs" / stamp / name, arm, logdir, args.model)
        except Exception as e:  # a crashed run is a failed run, with the reason kept
            res = {"pass": False, "error": repr(e)}
        res.update(scenario=sid, arm=arm, run=i, seconds=round(time.time() - t0))
        (logdir / "result.json").write_text(json.dumps(res, indent=2))
        print(f"{name}: {'PASS' if res['pass'] else 'FAIL'}", flush=True)
        return res

    with ThreadPoolExecutor(args.parallel) as pool:
        results = list(pool.map(one, jobs))

    summary = {}
    for r in results:
        key = f"{r['scenario']} {r['arm']}"
        s = summary.setdefault(key, {"passed": 0, "runs": 0,
                                     "rate": getattr(load(r["scenario"]), "PASS_RATE", 0.8)})
        s["runs"] += 1
        s["passed"] += bool(r["pass"])
    for s in summary.values():
        s["meets_rate"] = s["passed"] >= s["rate"] * s["runs"]
    (out / "summary.json").write_text(json.dumps({"model": args.model, "summary": summary,
                                                   "results": results}, indent=2))
    print(f"\nResults: {out}")
    for key, s in summary.items():
        verdict = "meets" if s["meets_rate"] else "below"
        print(f"  {key}: {s['passed']}/{s['runs']} ({verdict} its rate of {s['rate']:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
