"""The eval ledger, the comparison and readings (docs/projects/2026-11-06-metrics).

Each test names the design brief's test it proves (T1, T3, T5-T12). Eval
passes run on a copy of the runner and the tools in a temporary git
repository, with stub scenarios and a fake `claude`, so nothing costs API
usage and the real ledger is never written.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import metrics  # noqa: E402

COPIED = ["evals/run.py", "evals/lib.py", "evals/repos.json", "tools/metrics.py",
          "tools/factory.py", ".gitignore"]

STUB = '''import lib
PASS_RATE = 0.8


def run(dest, arm, logdir, model):
    dest.mkdir(parents=True, exist_ok=True)
    agent = lib.run_agent(dest, "task", logdir / "task.jsonl", model)
    return {"pass": %s, "cost_usd": agent.cost_usd, "judge": {"reason": "JUDGE-TEXT"},
            "final_reply": "REPLY-TEXT"}
'''

FAKE_CLAUDE = f'''#!{sys.executable}
import json
print(json.dumps({{"type": "assistant", "message": {{"content": [
    {{"type": "tool_use", "name": "Skill", "input": {{"skill": "retro"}}}}]}}}}))
print(json.dumps({{"type": "result", "result": "done", "total_cost_usd": 0.25,
                  "num_turns": 4, "is_error": False}}))
'''

# Logs every call, then runs the real command (git) or nothing (gh).
LOGGER = '''#!{python}
import json, os, sys
with open({log!r}, "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
real = {real!r}
if real:
    os.execv(real, [real, *sys.argv[1:]])
'''

READ_ONLY_GIT = {"rev-parse", "status", "diff", "ls-files", "log"}

FORBIDDEN_KEYS = {"score", "verdict", "grade", "rank", "ranking", "headline", "best", "worst",
                  "good", "bad", "better", "worse", "improved", "regressed", "meets_rate",
                  "status", "target", "goal", "gate", "by_author", "authors", "repositories"}


def git(cwd, *args, env=None):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@invalid", *args],
                          cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


def keys_and_strings(obj):
    """Every dict key and every string value in a JSON document."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield "key", k
            yield from keys_and_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys_and_strings(v)
    elif isinstance(obj, str):
        yield "str", obj


class Temp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)


class Factory(Temp):
    """A copy of the runner and tools in a fresh git repository."""

    def setUp(self):
        super().setUp()
        self.factory = self.tmp / "factory"
        for rel in COPIED:
            dest = self.factory / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dest)
        self.write("evals/scenarios/s1.py", STUB % 'arm != "bare"')
        self.write("evals/scenarios/s2.py", STUB % "False")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        claude = self.bin / "claude"
        claude.write_text(FAKE_CLAUDE)
        claude.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                        FACTORY_EVAL_DIR=str(self.tmp / "scratch"))
        git(self.factory, "init", "-q", "-b", "main")
        self.commit("Start the factory")

    def write(self, rel, text):
        p = self.factory / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, message):
        git(self.factory, "add", "-A")
        git(self.factory, "commit", "-qm", message)

    def head(self):
        return git(self.factory, "rev-parse", "--short=12", "HEAD").strip()

    def evals(self, *args):
        out = subprocess.run([sys.executable, "-B", str(self.factory / "evals" / "run.py"), *args],
                             capture_output=True, text=True, env=self.env)
        return out.returncode, out.stdout + out.stderr

    def tool(self, *args):
        out = subprocess.run([sys.executable, "-B", str(self.factory / "tools" / "metrics.py"), *args],
                             capture_output=True, text=True, env=self.env, cwd=self.factory)
        return out.returncode, out.stdout, out.stderr

    def ledger(self):
        return metrics.read(self.factory / "evals" / "ledger.jsonl")

    def compare(self, *versions):
        code, out, err = self.tool("compare", *versions)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def row(self, data, group, metric):
        return next(r for r in data["rows"] if r["group"] == group and r["metric"] == metric)

    def log_calls(self, name, real):
        log = self.tmp / f"{name}.log"
        script = self.bin / name
        script.write_text(LOGGER.format(python=sys.executable, log=str(log), real=real))
        script.chmod(0o755)
        return log


class Record(Factory):
    def test_t1_both_passes_are_kept_with_their_versions(self):
        code, out = self.evals("S1", "--arms", "preinstalled,bare", "--runs", "2")
        self.assertEqual(code, 0, out)
        clean = self.head()
        self.write("evals/scenarios/s1.py", STUB % 'arm != "bare"' + "# a draft change\n")
        code, out = self.evals("S1", "--runs", "1")
        self.assertEqual(code, 0, out)
        passes = [e for e in self.ledger() if e["kind"] == "pass"]
        self.assertEqual(len(passes), 2)
        self.assertEqual(passes[0]["version"], clean)
        self.assertIsNone(passes[0]["state"])
        self.assertEqual(passes[1]["version"], clean + "-modified")
        self.assertRegex(passes[1]["state"], r"^[0-9a-f]{8}$")
        self.assertEqual(len(passes[0]["runs"]), 4)

    def test_t1_the_ledger_alone_does_not_make_a_version_modified(self):
        self.evals("S1", "--runs", "1")
        self.evals("S1", "--runs", "1", "--arms", "bare")
        versions = [e["version"] for e in self.ledger()]
        self.assertEqual(versions, [self.head()] * 2)

    def test_t1_two_uncommitted_states_on_one_commit_stay_apart(self):
        self.write("evals/scenarios/s1.py", STUB % 'arm != "bare"' + "# draft one\n")
        self.evals("S1", "--runs", "1")
        self.write("evals/scenarios/s1.py", STUB % 'arm != "bare"' + "# draft two\n")
        self.evals("S1", "--runs", "1")
        keys = [metrics.key_of(e) for e in self.ledger()]
        self.assertEqual(len(set(keys)), 2)

    def test_c4_turns_and_skills_are_saved_per_run(self):
        self.evals("S1", "--runs", "1")
        run = self.ledger()[0]["runs"][0]
        self.assertEqual(run["turns"], 4)
        self.assertEqual(run["skills"], ["retro"])
        self.assertEqual(run["cost_usd"], 0.25)

    def test_n5_no_judge_text_or_reply_reaches_the_ledger(self):
        self.evals("S1", "--runs", "1")
        text = (self.factory / "evals" / "ledger.jsonl").read_text()
        self.assertNotIn("JUDGE-TEXT", text)
        self.assertNotIn("REPLY-TEXT", text)

    def test_calibrate_appends_the_judges_agreement(self):
        self.write("evals/scenarios/s3.py", "def judge_accepts(text):\n    return 'yes' in text\n")
        self.write("evals/calibration/s3/good/a.txt", "yes")
        self.write("evals/calibration/s3/bad/b.txt", "yes")
        code, out = self.evals("S3", "--calibrate")
        self.assertEqual(code, 1, out)  # a judge that disagrees still fails calibration
        cal = self.ledger()[-1]
        self.assertEqual(cal["kind"], "calibration")
        self.assertEqual(cal["judges"], {"S3": {"samples": 2, "agreed": 1}})


class Compare(Factory):
    def two_versions(self):
        self.evals("S1", "--arms", "preinstalled,bare", "--runs", "2")
        first = self.head()
        self.write("README.md", "a change\n")
        self.commit("Change the factory")
        self.write("evals/scenarios/s1.py", STUB % 'arm == "bare"')
        self.commit("Make S1 fail on the factory arm")
        self.evals("S1", "--arms", "preinstalled,bare", "--runs", "2")
        return first, self.head()

    def test_t5_two_versions_show_both_values_and_the_change(self):
        first, second = self.two_versions()
        data = self.compare(first, second)
        self.assertEqual([v["version"] for v in data["versions"]], [first, second])
        cells = self.row(data, "S1 preinstalled", "pass_rate")["cells"]
        self.assertEqual([c["value"] for c in cells], [1.0, 0.0])
        self.assertEqual(cells[1]["change"], -1.0)
        self.assertEqual(cells[1]["change_from"], first)
        lift = self.row(data, "S1 preinstalled", "lift_over_bare")["cells"]
        self.assertEqual([c["value"] for c in lift], [1.0, -1.0])

    def test_t3_every_number_carries_a_definition_a_source_and_a_count(self):
        self.two_versions()
        data = self.compare()
        self.assertTrue(data["rows"])
        for row in data["rows"]:
            self.assertTrue(row["definition"].strip(), row["metric"])
            for c in row["cells"]:
                self.assertTrue(c["source"].strip(), row)
                self.assertIsInstance(c["count"], int)
                if not c["missing"]:
                    self.assertIn("pass ", c["source"])

    def test_t6_a_number_a_version_lacks_is_missing_not_zero(self):
        ledger = self.factory / "evals" / "ledger.jsonl"
        metrics.append(ledger, [{  # an older pass, recorded before turns and skills were kept
            "kind": "pass", "id": "20261101-000000-S1", "version": "000000000000", "state": None,
            "date": "2026-11-01T00:00", "model": "opus", "source": "imported",
            "pass_marks": {"S1 preinstalled": 0.8},
            "runs": [{"scenario": "S1", "arm": "preinstalled", "run": 1, "pass": True, "void": None,
                      "crashed": False, "cost_usd": 0.5, "seconds": 10, "turns": None, "skills": None}]}])
        self.evals("S1", "--runs", "1")
        data = self.compare()
        old, new = self.row(data, "S1 preinstalled", "turns_per_run")["cells"]
        self.assertEqual((old["value"], old["missing"]), (None, True))
        self.assertEqual((new["value"], new["missing"]), (4, False))
        self.assertIsNone(new["change"])
        old, new = self.row(data, "S1 preinstalled", "runs_using_skill:retro")["cells"]
        self.assertTrue(old["missing"])
        self.assertEqual(new["value"], 1)
        old, new = self.row(data, "S1 preinstalled", "void")["cells"]
        self.assertTrue(old["missing"])
        self.assertEqual(new["value"], 0)
        # the numbers both versions have still compare
        old, new = self.row(data, "S1 preinstalled", "cost_per_run_usd")["cells"]
        self.assertEqual(new["change"], -0.25)

    def test_t6_a_scenario_a_version_did_not_run_is_missing(self):
        self.evals("S1", "--runs", "1")
        self.write("README.md", "x\n")
        self.commit("next")
        self.evals("S2", "--runs", "1")
        data = self.compare()
        cells = self.row(data, "S2 preinstalled", "passed")["cells"]
        self.assertEqual((cells[0]["value"], cells[0]["missing"]), (None, True))
        self.assertEqual(cells[1]["value"], 0)

    def test_t8_compare_prints_json_and_renders_no_page(self):
        self.evals("S1", "--runs", "1")
        code, out, err = self.tool("compare")
        self.assertEqual(code, 0, err)
        json.loads(out)
        self.assertFalse((self.factory / ".scratch").exists())

    def test_the_page_shows_every_version_and_the_readings(self):
        first, second = self.two_versions()
        self.tool("add-reading", "--about", first, second, "--author", "maintainer",
                  "--text", "S1 flipped & the bare arm with it")
        code, out, err = self.tool("compare", "--html")
        self.assertEqual(code, 0, err)
        page = (self.factory / metrics.DEFAULT_PAGE).read_text()
        self.assertIn("<h1>", page)
        self.assertIn(first, page)
        self.assertIn(second, page)
        self.assertIn("S1 flipped &amp; the bare arm with it", page)
        self.assertNotRegex(page, r'(src|href)="(https?:)?//')  # no external requests

    def test_the_page_stays_inside_the_repository(self):
        self.evals("S1", "--runs", "1")
        code, _, err = self.tool("compare", "--html", "../outside.html")
        self.assertEqual(code, 1)
        self.assertFalse((self.tmp / "outside.html").exists())


class Readings(Factory):
    def test_t7_two_readings_on_one_comparison_are_both_kept(self):
        self.evals("S1", "--runs", "1")
        v = self.head()
        before = (self.factory / "evals" / "ledger.jsonl").read_text()
        for who, text in (("maintainer", "Looks like noise to me."), ("an agent", "Turns fell; cost too.")):
            code, _, err = self.tool("add-reading", "--about", v, "--author", who, "--text", text)
            self.assertEqual(code, 0, err)
        after = (self.factory / "evals" / "ledger.jsonl").read_text()
        self.assertTrue(after.startswith(before))  # appended, nothing rewritten
        readings = self.compare(v)["readings"]
        self.assertEqual([r["author"] for r in readings], ["maintainer", "an agent"])
        self.assertEqual([r["text"] for r in readings], ["Looks like noise to me.", "Turns fell; cost too."])
        for r in readings:
            self.assertRegex(r["date"], r"^\d{4}-\d\d-\d\dT")
            self.assertEqual(r["about"], [v])

    def test_a_reading_names_versions_that_exist(self):
        self.evals("S1", "--runs", "1")
        code, _, err = self.tool("add-reading", "--about", "ffffff", "--author", "x", "--text", "y")
        self.assertEqual(code, 1)
        self.assertIn("no version", err)

    def test_a_reading_is_a_short_note(self):
        self.evals("S1", "--runs", "1")
        code, _, _ = self.tool("add-reading", "--about", self.head(), "--author", "x",
                               "--text", "y" * (metrics.MAX_READING + 1))
        self.assertEqual(code, 1)


class StaysInTheRepository(Factory):
    def test_t9_writes_only_inside_the_repository_and_never_pushes_or_posts(self):
        self.evals("S1", "--runs", "1")
        results = self.tmp / "results.json"
        results.write_text(json.dumps({"model": "opus", "passes": [{
            "pass": "S1", "started": "20991231-000000", "note": "a note",
            "summary": {"S1 preinstalled": {"passed": 1, "runs": 1, "void": 0, "rate": 0.8}},
            "runs": [{"pass": True, "scenario": "S1", "arm": "preinstalled", "run": 1,
                      "cost_usd": 0.1, "seconds": 5}]}]}))
        git_log = self.log_calls("git", shutil.which("git"))
        gh_log = self.log_calls("gh", "")
        outside = lambda: sorted(  # noqa: E731
            str(p) for p in self.tmp.rglob("*")
            if self.factory not in p.parents and p.parent != self.bin and not p.name.endswith(".log"))
        before = outside()
        v = self.head()
        for args in (("versions",), ("compare", "--html"), ("import-results", str(results)),
                     ("add-reading", "--about", v, "--author", "an agent", "--text", "noted")):
            code, _, err = self.tool(*args)
            self.assertEqual(code, 0, (args, err))
        self.assertEqual(outside(), before)
        self.assertFalse(gh_log.exists(), "gh was called")
        for call in map(json.loads, git_log.read_text().splitlines()):
            args = call[2:] if call[:1] == ["-C"] else call
            self.assertIn(args[0], READ_ONLY_GIT, call)
        changed = git(self.factory, "status", "--porcelain").split()
        self.assertEqual(changed, ["??", "evals/ledger.jsonl"])

    def test_t9_an_eval_pass_only_reads_git_and_never_calls_gh(self):
        git_log = self.log_calls("git", shutil.which("git"))
        gh_log = self.log_calls("gh", "")
        code, out = self.evals("S1", "--runs", "1")
        self.assertEqual(code, 0, out)
        self.assertFalse(gh_log.exists())
        for call in map(json.loads, git_log.read_text().splitlines()):
            args = call[2:] if call[:1] == ["-C"] else call
            self.assertIn(args[0], READ_ONLY_GIT, call)


class NoVerdict(Factory):
    def setUp(self):
        super().setUp()
        self.evals("S1", "--arms", "preinstalled,bare", "--runs", "2")
        self.tool("add-reading", "--about", self.head(), "--author", "maintainer", "--text", "fine")

    def test_t10_no_field_is_a_score_or_a_verdict_and_no_lines_of_code(self):
        for command in (("compare",), ("versions",)):
            _, out, _ = self.tool(*command)
            for kind, value in keys_and_strings(json.loads(out)):
                if kind == "key":
                    self.assertNotIn(value.lower(), FORBIDDEN_KEYS, command)
                    self.assertNotIn("line", value.lower(), command)
        data = self.compare()
        for row in data["rows"]:
            self.assertNotIn(row["metric"], FORBIDDEN_KEYS)
            self.assertNotIn("line", row["metric"])
            for c in row["cells"]:
                self.assertNotIsInstance(c["value"], str)  # numbers only, no labels like good/bad

    def test_t10_the_pass_mark_is_only_the_value_recorded_with_the_scenario(self):
        data = self.compare()
        recorded = {k: v for e in self.ledger() if e["kind"] == "pass" for k, v in e["pass_marks"].items()}
        marks = [r for r in data["rows"] if r["metric"] == "pass_mark"]
        self.assertEqual({r["group"] for r in marks}, set(recorded))
        for r in marks:
            self.assertEqual({c["value"] for c in r["cells"]}, {recorded[r["group"]]})
        text = json.dumps(data)
        self.assertNotIn("meets", text)
        self.assertNotIn("below", text)

    def test_t11_no_headline_and_one_version_alone_shows_all_its_numbers(self):
        data = self.compare(self.head())
        self.assertEqual(set(data), {"about", "ledger", "versions", "rows", "readings"})
        metrics_shown = {(r["group"], r["metric"]) for r in data["rows"]}
        every = {(g, m) for g, nums in metrics.numbers_of(self.ledger(), self.head()).items() for m in nums}
        self.assertEqual(metrics_shown, every)
        self.assertIsInstance(data["readings"], list)  # in ledger order, not grouped by author
        page_code, _, _ = self.tool("compare", "--html")
        page = (self.factory / metrics.DEFAULT_PAGE).read_text()
        for _, m in every:
            self.assertIn(m, page)
        self.assertNotIn("headline", page.lower())

    def test_t12_the_exit_code_is_the_same_whatever_the_numbers(self):
        self.write("README.md", "x\n")
        self.commit("next")
        code, out = self.evals("S2", "--runs", "2")  # every run fails
        self.assertEqual(code, 0, out)
        self.assertIn("S2 preinstalled: 0/2 (below its rate of 80%)", out)  # the runner's own report
        for args in (("compare",), ("compare", "--html"), ("versions",)):
            self.assertEqual(self.tool(*args)[0], 0, args)

    def test_t12_a_ledger_that_cannot_be_written_changes_nothing_else(self):
        ledger = self.factory / "evals" / "ledger.jsonl"
        ledger.unlink()
        ledger.mkdir()  # appending to a directory fails
        code, out = self.evals("S2", "--runs", "1")
        self.assertEqual(code, 0, out)
        self.assertIn("Ledger not updated", out)
        self.assertIn("S2 preinstalled: 0/1 (below its rate of 80%)", out)


class Import(Temp):
    """C3: the hand-picked results file becomes the ledger's first entries."""

    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "factory"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        for n, when in enumerate(("2026-11-04T19:39:15-0800", "2026-11-05T08:18:41-0800")):
            (self.repo / "f").write_text(str(n))
            git(self.repo, "add", "-A")
            env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
            git(self.repo, "commit", "-qm", f"c{n}", env=env)
        self.shas = git(self.repo, "log", "--format=%h", "--abbrev=12").split()[::-1]
        self.results = self.repo / "results.json"
        self.results.write_text(json.dumps({"model": "opus", "passes": [
            {"pass": "T9", "started": "20261105-065701", "note": "T9 1/3",
             "summary": {"T9 preinstalled": {"passed": 1, "runs": 1, "rate": 0.8, "meets_rate": False}},
             "runs": [{"pass": False, "judge": {"reason": "JUDGE-TEXT"}, "cost_usd": 2.9,
                       "scenario": "T9", "arm": "preinstalled", "run": 1, "seconds": 128}]},
            {"pass": "T7", "started": "20261105-100211", "note": "T7 later",
             "summary": {"T7 preinstalled": {"passed": 1, "runs": 1, "void": 0, "rate": 0.8}},
             "runs": [{"pass": True, "cost_usd": 0.5, "scenario": "T7", "arm": "preinstalled",
                       "run": 1, "seconds": 80, "skills_used": ["create-pr"]}]}]}))

    def test_passes_get_the_commit_before_them_and_notes_become_readings(self):
        added = metrics.import_results(self.results, self.repo)
        passes = [e for e in added if e["kind"] == "pass"]
        self.assertEqual([p["version"] for p in passes], [s + "-modified" for s in self.shas])
        self.assertEqual(passes[0]["source"], "imported from results.json")
        self.assertIsNone(passes[0]["runs"][0]["void"])  # the runner didn't record void yet
        self.assertFalse(passes[1]["runs"][0]["void"])
        self.assertEqual(passes[1]["runs"][0]["skills"], ["create-pr"])
        readings = [e for e in added if e["kind"] == "reading"]
        self.assertEqual([r["text"] for r in readings], ["T9 1/3", "T7 later"])
        self.assertEqual(readings[0]["about"], [metrics.key_of(passes[0])])
        self.assertNotIn("JUDGE-TEXT", (self.repo / metrics.LEDGER).read_text())

    def test_importing_twice_adds_nothing(self):
        metrics.import_results(self.results, self.repo)
        self.assertEqual(metrics.import_results(self.results, self.repo), [])
        self.assertEqual(len(metrics.read(self.repo / metrics.LEDGER)), 4)


class Ledger(Temp):
    def test_k4_parallel_appends_all_land_whole(self):
        path = self.tmp / "ledger.jsonl"
        big = "x" * 20000
        threads = [threading.Thread(target=metrics.append, args=(path, [{"id": i, "pad": big}]))
                   for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(e["id"] for e in metrics.read(path)), list(range(16)))

    def test_a_line_twice_after_a_union_merge_counts_once(self):
        path = self.tmp / "ledger.jsonl"
        metrics.append(path, [{"id": 1}, {"id": 2}])
        path.write_text(path.read_text() + '{"id":1}\n')
        self.assertEqual(metrics.read(path), [{"id": 1}, {"id": 2}])

    def test_the_committed_ledger_reads_and_compares(self):
        entries = metrics.read(ROOT / metrics.LEDGER)
        self.assertTrue(any(e["kind"] == "pass" for e in entries))
        data = metrics.compare(entries)
        self.assertTrue(data["rows"])


if __name__ == "__main__":
    unittest.main()
