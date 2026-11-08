#!/usr/bin/env python3
"""Run scenario evals and report a pass rate per scenario and arm.

    python3 evals/run.py T1 --arms preinstalled,bare --runs 3
    python3 evals/run.py T1 --calibrate

--calibrate checks each scenario's judge against the known-good and known-bad
samples in evals/calibration/<id>/ instead of running agents; a judge that
disagrees with any sample isn't trusted.

Each run gets its own snapshot of the scenario's repository in a scratch
folder (FACTORY_EVAL_DIR, default: the system temp dir). Results land in
<scratch>/results/<timestamp>/ as one JSON per run plus summary.json; a batch
started in the same second as another gets <timestamp>.2 and so on.

Every pass, and every --calibrate, also appends its numbers (no judge text or
replies) to the committed ledger, evals/ledger.jsonl, with the factory version
they measured. Compare versions with tools/metrics.py.
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
sys.path.insert(1, str(Path(__file__).resolve().parent.parent / "tools"))
import lib  # noqa: E402
import metrics  # noqa: E402


def load(scenario_id: str):
    return importlib.import_module(f"scenarios.{scenario_id.lower()}")


def calibrate(scenario_ids: list[str]) -> int:
    root = Path(__file__).resolve().parent / "calibration"
    wrong = 0
    judges = {}
    for sid in scenario_ids:
        mod = load(sid)
        tally = judges.setdefault(sid, {"samples": 0, "agreed": 0})
        for want, folder in ((True, "good"), (False, "bad")):
            for sample in sorted((root / sid.lower() / folder).glob("*")):
                got = mod.judge_accepts(sample.read_text())
                ok = got == want
                wrong += not ok
                tally["samples"] += 1
                tally["agreed"] += ok
                print(f"{sid} {folder}/{sample.name}: judge {'accepts' if got else 'rejects'}"
                      f" {'ok' if ok else 'WRONG'}", flush=True)
    print("calibrated" if not wrong else f"{wrong} sample(s) judged wrong: fix the judge first")
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-calibrate-" + "-".join(scenario_ids)
    keep_in_ledger(lambda: metrics.record_calibration(stamp, judges))
    return 1 if wrong else 0


def keep_in_ledger(record) -> None:
    """Append to the ledger; a ledger that can't be written never changes the outcome."""
    try:
        entry = record()
    except Exception as e:
        print(f"Ledger not updated: {e!r}", file=sys.stderr)
        return
    print(f"Ledger: {entry['kind']} {entry['id']} on {metrics.key_of(entry)} -> {metrics.LEDGER}")


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

    stamp = lib.claim_batch(time.strftime("%Y%m%d-%H%M%S") + "-" + "-".join(args.scenarios))
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
        started = lib.agents_started()
        lib.reset_sessions()
        try:
            res = mod.run(lib.workdir() / "runs" / stamp / name, arm, logdir, args.model)
        except lib.UsageLimit as e:  # cut short by the account, not judged: void
            res = {"pass": None, "void": f"usage limit: {e}"}
        except Exception as e:
            if lib.agents_started() == started:  # setup broke before any agent ran: void
                res = {"pass": None, "void": f"setup error: {e!r}"}
            else:  # a crashed run is a failed run, with the reason kept
                res = {"pass": False, "error": repr(e)}
        res.update(scenario=sid, arm=arm, run=i, seconds=round(time.time() - t0),
                   **lib.session_numbers())
        (logdir / "result.json").write_text(json.dumps(res, indent=2))
        verdict = "VOID" if res["pass"] is None else "PASS" if res["pass"] else "FAIL"
        print(f"{name}: {verdict}", flush=True)
        return res

    with ThreadPoolExecutor(args.parallel) as pool:
        results = list(pool.map(one, jobs))

    summary = {}
    for r in results:
        key = f"{r['scenario']} {r['arm']}"
        s = summary.setdefault(key, {"passed": 0, "runs": 0, "void": 0,
                                     "rate": getattr(load(r["scenario"]), "PASS_RATE", 0.8)})
        if r["pass"] is None:
            s["void"] += 1
            continue
        s["runs"] += 1
        s["passed"] += bool(r["pass"])
    for s in summary.values():  # a voided run means the rate isn't shown either way
        s["meets_rate"] = not s["void"] and s["passed"] >= s["rate"] * s["runs"]
    (out / "summary.json").write_text(json.dumps({"model": args.model, "summary": summary,
                                                   "results": results}, indent=2))
    print(f"\nResults: {out}")
    for key, s in summary.items():
        if s["void"]:
            print(f"  {key}: {s['passed']}/{s['runs']}, {s['void']} void (see result.json): rerun")
            continue
        verdict = "meets" if s["meets_rate"] else "below"
        print(f"  {key}: {s['passed']}/{s['runs']} ({verdict} its rate of {s['rate']:.0%})")
    keep_in_ledger(lambda: metrics.record_pass(stamp, args.model, results, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
