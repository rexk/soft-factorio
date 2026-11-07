"""A repository's own numbers, from the metrics skill (docs/projects/2026-11-06-metrics, stages 2 and 3).

Each test names the design brief's test it proves (T2 and T4, and T3,
T5-T12 for repository numbers) or the risk it covers (K1, K3). Every repository is a
temporary git repository with dated commits; its pull requests come from
the fake `gh` (evals/fakes/gh), so nothing touches a network. The script
runs from where the factory installs it, .agents/skills/metrics/, inside
the temporary repository.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "metrics"
sys.path.insert(0, str(ROOT / "tools"))
import factory  # noqa: E402

spec = importlib.util.spec_from_file_location("repo_metrics", SKILL / "metrics.py")
rm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rm)

V1, V2 = "1111111aaaaa", "2222222bbbbb"
INSTALLED = ".agents/skills/metrics"

# Logs every call, then runs the real git.
LOGGER = '''#!{python}
import json, os, sys
with open({log!r}, "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
os.execv({real!r}, [{real!r}, *sys.argv[1:]])
'''
FAILING_GH = '''#!{python}
import sys
print("To get started with GitHub CLI, please run:  gh auth login", file=sys.stderr)
sys.exit(4)
'''
READ_ONLY_GIT = {"rev-parse", "log", "show"}

FORBIDDEN_KEYS = {"score", "verdict", "grade", "rank", "ranking", "headline", "best", "worst",
                  "good", "bad", "better", "worse", "improved", "regressed", "meets_rate",
                  "status", "target", "goal", "gate", "by_author", "authors", "repositories"}

LESSONS_TWO = """Adds the parser.

## Lessons

| Correction (their words) | Cause | Fix: test, rule, skill or nothing | Why this stops it recurring |
|---|---|---|---|
| "use the real date" | the code allowed it | a test: `tests/test_dates.py` | fails on the wrong date |
| "typo in the title" | a one-off | nothing | already fixed |
"""
LESSONS_ONE = """## Lessons

| Correction (their words) | Cause | Fix: test, rule, skill or nothing | Why this stops it recurring |
|---|---|---|---|
| "always ask before deploys" | a convention | a rule in `AGENTS.md` | agents read it first |
"""


def git(cwd, *args, when=None):
    env = dict(os.environ)
    if when:
        env.update(GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@invalid", *args],
                          cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


def keys_and_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield "key", k
            yield from keys_and_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys_and_strings(v)
    elif isinstance(obj, str):
        yield "str", obj


def pr(number, branch, created, state="MERGED", merged=None, sha=None, body="", reviews=(), commits=()):
    return {"number": number, "headRefName": branch, "state": state, "createdAt": created,
            "mergedAt": merged, "mergeCommit": {"oid": sha} if sha else None, "body": body,
            "reviews": [{"state": s, "submittedAt": t} for s, t in reviews],
            "commits": [{"messageHeadline": h, "messageBody": b} for h, b in commits]}


class Repo(unittest.TestCase):
    """Commits before the factory, then two factory versions, and pull requests in each."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        shutil.copy(ROOT / "evals" / "fakes" / "gh", self.bin / "gh")
        (self.bin / "gh").chmod(0o755)
        self.gh_log = self.tmp / "gh.jsonl"
        self.prs_file = self.tmp / "prs.json"
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                        FAKE_GH_LOG=str(self.gh_log), FAKE_GH_PRS=str(self.prs_file))
        self.build()

    def commit(self, message, when, files=None):
        for rel, text in (files or {"work.txt": message}).items():
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", message, when=when)
        return git(self.repo, "rev-parse", "HEAD").strip()

    def apply(self, version, when, install=False):
        files = {".agents/factory/manifest.json": json.dumps({"version": version, "files": {}})}
        if install:  # what an apply copies: the skill's folder, nothing else of the factory
            for f in ("metrics.py", "metrics_ledger.py", "SKILL.md"):
                files[f"{INSTALLED}/{f}"] = (SKILL / f).read_text()
        return self.commit(f"Apply the factory {version}", when, files)

    def build(self):
        self.commit("Start", "2026-01-01T09:00:00+0000")
        a = self.commit("Add feature a", "2026-01-05T09:00:00+0000")
        self.commit(f'Revert "Add feature a"\n\nThis reverts commit {a}.', "2026-01-08T09:00:00+0000")
        self.apply(V1, "2026-02-01T09:00:00+0000", install=True)
        self.m1 = self.commit("Parse dates", "2026-02-10T12:00:00+0000")
        self.commit(f'Revert "Parse dates"\n\nThis reverts commit {self.m1}.', "2026-02-12T09:00:00+0000")
        self.commit("Resolve a conflict on reapply", "2026-02-20T09:00:00+0000",  # same version: no new one
                    {".agents/factory/manifest.json": json.dumps({"version": V1, "files": {"a": "b"}})})
        self.apply(V2, "2026-03-01T09:00:00+0000")
        self.m2 = self.commit("Deploy check", "2026-03-05T00:00:00+0000")
        self.commit(f'Revert "Docs"\n\nThis reverts commit {"12" * 20}.',  # 22 days after #8 merged
                    "2026-03-25T00:00:00+0000")
        self.write_prs([
            # before the factory
            pr(1, "fix-typo", "2026-01-03T00:00:00Z", merged="2026-01-04T00:00:00Z", sha="ab" * 20),
            pr(2, "claude/try-a", "2026-01-10T00:00:00Z", state="CLOSED"),
            pr(3, "feature", "2026-01-15T10:00:00Z", merged="2026-01-16T10:00:00Z", sha="cd" * 20,
               reviews=[("COMMENTED", "2026-01-15T12:00:00Z"), ("APPROVED", "2026-01-16T09:00:00Z")],
               commits=[("Add b", "Co-Authored-By: Claude <noreply@anthropic.com>")]),
            # factory V1
            pr(4, "codex/dates", "2026-02-05T12:00:00Z", merged="2026-02-10T12:00:00Z", sha=self.m1,
               body=LESSONS_TWO, reviews=[("CHANGES_REQUESTED", "2026-02-06T00:00:00Z"),
                                          ("COMMENTED", "2026-02-07T00:00:00Z"),
                                          ("APPROVED", "2026-02-10T00:00:00Z"),
                                          ("COMMENTED", "2026-02-11T00:00:00Z")]),
            pr(5, "topic", "2026-02-15T00:00:00Z", state="OPEN",
               body="Does a thing.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"),
            pr(6, "people-work", "2026-02-16T00:00:00Z", merged="2026-02-17T00:00:00Z", sha="ef" * 20),
            # factory V2
            pr(7, "claude/deploy", "2026-03-02T00:00:00Z", merged="2026-03-05T00:00:00Z", sha=self.m2,
               body=LESSONS_ONE),
            pr(8, "claude/docs", "2026-03-03T00:00:00Z", merged="2026-03-03T06:00:00Z", sha="12" * 20),
        ])

    def write_prs(self, prs):
        self.prs_file.write_text(json.dumps(prs))

    def run_tool(self, *args, env=None):
        out = subprocess.run([sys.executable, "-B", str(self.repo / INSTALLED / "metrics.py"), *args],
                             capture_output=True, text=True, env=env or self.env, cwd=self.repo)
        return out.returncode, out.stdout, out.stderr

    def compare(self, *args, env=None):
        code, out, err = self.run_tool("compare", *args, env=env)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def values(self, data, metric):
        row = next(r for r in data["rows"] if r["metric"] == metric)
        return {c["version"]: c["value"] for c in row["cells"]}

    def cells(self, data, metric):
        row = next(r for r in data["rows"] if r["metric"] == metric)
        return {c["version"]: c for c in row["cells"]}

    def log_git(self):
        log = self.tmp / "git.log"
        script = self.bin / "git"
        script.write_text(LOGGER.format(python=sys.executable, log=str(log), real=shutil.which("git")))
        script.chmod(0o755)
        return log


class Numbers(Repo):
    def test_t2_before_the_factory_and_each_version_with_nothing_configured(self):
        self.assertFalse((self.repo / rm.LEDGER).exists())
        data = self.compare()
        self.assertEqual([v["version"] for v in data["versions"]], [rm.BEFORE, V1, V2])
        self.assertEqual(self.values(data, "agent_prs_opened"), {rm.BEFORE: 2, V1: 2, V2: 2})
        self.assertEqual(self.values(data, "agent_prs_merged"), {rm.BEFORE: 1, V1: 1, V2: 2})
        self.assertEqual(self.values(data, "agent_prs_still_open"), {rm.BEFORE: 0, V1: 1, V2: 0})
        self.assertEqual(self.values(data, "agent_pr_merge_rate"), {rm.BEFORE: 0.5, V1: 1.0, V2: 1.0})
        self.assertEqual(self.values(data, "review_rounds_per_merged_pr"), {rm.BEFORE: 1.0, V1: 2.0, V2: 0.0})
        self.assertEqual(self.values(data, "hours_to_merge_median"), {rm.BEFORE: 24.0, V1: 120.0, V2: 39.0})
        self.assertEqual(self.values(data, "reverted_within_14_days"), {rm.BEFORE: 0, V1: 1, V2: 0})
        self.assertEqual(self.values(data, "revert_commits"), {rm.BEFORE: 1, V1: 1, V2: 1})
        self.assertEqual(self.values(data, "corrections_per_pr"), {rm.BEFORE: None, V1: 2.0, V2: 1.0})
        self.assertEqual(self.values(data, "corrections_with_a_fix"), {rm.BEFORE: None, V1: 1, V2: 1})
        self.assertFalse((self.repo / rm.LEDGER).exists(), "numbers are computed, not stored")

    def test_t2_versions_come_from_the_manifest_history(self):
        code, out, err = self.run_tool("versions")
        self.assertEqual(code, 0, err)
        vs = json.loads(out)
        self.assertEqual([v["label"] for v in vs], ["before the factory", V1, V2])
        self.assertEqual([v["spans"][0]["from"][:10] for v in vs], ["2026-01-01", "2026-02-01", "2026-03-01"])
        self.assertEqual(vs[0]["spans"][0]["to"][:10], "2026-02-01")
        self.assertIsNone(vs[-1]["spans"][0]["to"])
        self.assertEqual([len(v["manifest_commits"]) for v in vs], [0, 1, 1])
        self.assertFalse(self.gh_log.exists(), "listing versions needs no pull requests")

    def test_t2_a_repository_that_never_applied_has_only_the_time_before(self):
        other = self.tmp / "plain"
        other.mkdir()
        git(other, "init", "-q", "-b", "main")
        (other / "f").write_text("x")
        git(other, "add", "-A")
        git(other, "commit", "-qm", "one", when="2026-01-01T00:00:00+0000")
        out = subprocess.run([sys.executable, "-B", str(SKILL / "metrics.py"), "compare", "--repo", str(other)],
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual([v["version"] for v in data["versions"]], [rm.BEFORE])
        self.assertIn("hasn't applied the factory", data["about"])

    def test_t2_a_repository_that_started_with_the_factory_has_no_time_before(self):
        other = self.tmp / "born"
        other.mkdir()
        git(other, "init", "-q", "-b", "main")
        (other / ".agents/factory").mkdir(parents=True)
        (other / ".agents/factory/manifest.json").write_text(json.dumps({"version": V1}))
        git(other, "add", "-A")
        git(other, "commit", "-qm", "one", when="2026-01-01T00:00:00+0000")
        self.assertEqual([v["version"] for v in rm.versions(other, "HEAD", rm.commits_of(other, "HEAD"))], [V1])

    def test_k1_the_agent_rule_is_the_source_and_people_s_prs_are_left_out(self):
        data = self.compare()
        self.assertIn("claude/", data["agent_rule"])
        self.assertIn("Co-Authored-By", data["agent_rule"])
        for metric in rm.DEFINITIONS:
            if rm.GROUP_OF[metric] != rm.HISTORY:
                for c in self.cells(data, metric).values():
                    self.assertIn(data["agent_rule"], c["source"], metric)
        src = self.cells(data, "agent_prs_opened")
        self.assertIn("#2, #3", src[rm.BEFORE]["source"])  # branch prefix; co-author trailer
        self.assertIn("#4, #5", src[V1]["source"])  # branch prefix; footer
        for c in src.values():
            self.assertNotIn("#1", c["source"])
            self.assertNotIn("#6", c["source"])
        self.assertEqual(src[V1]["count"], 3)  # opened in V1, anyone's

    def test_k1_another_branch_prefix_can_be_named(self):
        prs = json.loads(self.prs_file.read_text())
        prs[5]["headRefName"] = "bot/people-work"
        self.write_prs(prs)
        self.assertEqual(self.values(self.compare(), "agent_prs_opened")[V1], 2)
        data = self.compare("--agent-branch", "bot/")
        self.assertEqual(self.values(data, "agent_prs_opened")[V1], 3)
        self.assertIn("bot/", data["agent_rule"])

    def test_k3_lessons_rows_are_counted_when_a_table_is_found(self):
        self.assertEqual(rm.lessons(LESSONS_TWO), [['"use the real date"', "a test: `tests/test_dates.py`"],
                                                  ['"typo in the title"', "nothing"]])
        self.assertIsNone(rm.lessons("No table here.\n\n| a | b |\n|---|---|\n| 1 | 2 |"))
        self.assertIsNone(rm.lessons(None))
        empty = LESSONS_ONE.rsplit("\n", 2)[0] + "\n"  # the header and separator, no rows
        self.assertEqual(rm.lessons(empty), [])
        self.assertTrue(rm.names_a_fix("a rule in `AGENTS.md`"))
        self.assertFalse(rm.names_a_fix("nothing"))

    def test_k3_a_pull_request_without_a_table_is_missing_not_zero(self):
        data = self.compare(V2)
        with_table = self.cells(data, "agent_prs_with_lessons_table")[V2]
        self.assertEqual((with_table["value"], with_table["count"]), (1, 2))  # #8 has none
        per_pr = self.cells(data, "corrections_per_pr")[V2]
        self.assertEqual((per_pr["value"], per_pr["count"]), (1.0, 1))


class Compare(Repo):
    def test_t3_every_number_carries_a_definition_a_source_and_a_count(self):
        data = self.compare()
        self.assertEqual({r["metric"] for r in data["rows"]}, set(rm.DEFINITIONS))
        for row in data["rows"]:
            self.assertTrue(row["definition"].strip(), row["metric"])
            for c in row["cells"]:
                self.assertTrue(c["source"].strip(), row)
                self.assertIsInstance(c["count"], int)
                self.assertTrue(c["source"].startswith(("gh pr list", "git log", "Lessons tables")), c)

    def test_t5_two_versions_show_both_values_and_the_change(self):
        data = self.compare("before", V1)
        self.assertEqual([v["version"] for v in data["versions"]], [rm.BEFORE, V1])
        rate = self.cells(data, "agent_pr_merge_rate")
        self.assertEqual((rate[rm.BEFORE]["value"], rate[V1]["value"]), (0.5, 1.0))
        self.assertEqual(rate[V1]["change"], 0.5)
        self.assertEqual(rate[V1]["change_from"], rm.BEFORE)
        self.assertIsNone(rate[rm.BEFORE]["change"])
        hours = self.cells(self.compare(V1, V2), "hours_to_merge_median")[V2]
        self.assertEqual((hours["change"], hours["change_from"]), (-81.0, V1))

    def test_t6_a_number_a_version_lacks_is_missing_not_zero(self):
        data = self.compare()
        fix = self.cells(data, "corrections_with_a_fix")
        self.assertEqual((fix[rm.BEFORE]["value"], fix[rm.BEFORE]["missing"]), (None, True))
        self.assertIsNone(fix[V1]["change"])  # nothing to compare with
        self.assertEqual(fix[V2]["change"], 0)  # both there: compares

    def test_t6_without_pull_requests_their_numbers_are_missing_and_git_numbers_still_compare(self):
        failing = self.bin / "gh"
        failing.write_text(FAILING_GH.format(python=sys.executable))
        data = self.compare()
        for metric in rm.DEFINITIONS:
            for c in self.cells(data, metric).values():
                if rm.GROUP_OF[metric] == rm.HISTORY:
                    self.assertFalse(c["missing"])
                else:
                    self.assertEqual((c["value"], c["missing"], c["count"]), (None, True, 0), metric)
                    self.assertIn("gh auth login", c["source"])
        self.assertEqual(self.cells(data, "revert_commits")[V2]["change"], 0)

    def test_t6_without_gh_installed_the_numbers_say_so(self):
        only_git = self.tmp / "only-git"
        only_git.mkdir()
        (only_git / "git").symlink_to(shutil.which("git"))
        data = self.compare(env=dict(self.env, PATH=str(only_git)))
        c = self.cells(data, "agent_prs_opened")[V1]
        self.assertTrue(c["missing"])
        self.assertIn("isn't installed", c["source"])

    def test_t6_reading_only_the_newest_prs_says_so(self):
        data = self.compare("--limit", "3")
        self.assertIn("the newest 3 only", self.cells(data, "agent_prs_opened")[V2]["source"])

    def test_t8_compare_prints_json_and_renders_no_page(self):
        code, out, err = self.run_tool("compare")
        self.assertEqual(code, 0, err)
        json.loads(out)
        self.assertFalse((self.repo / ".scratch").exists())

    def test_the_page_shows_every_version_and_the_readings(self):
        self.run_tool("add-reading", "--about", V1, "--author", "maintainer", "--text", "merges up & reverts too")
        code, _, err = self.run_tool("compare", "--html")
        self.assertEqual(code, 0, err)
        page = (self.repo / rm.DEFAULT_PAGE).read_text()
        self.assertIn("<h1>", page)
        for text in ("before the factory", V1, V2, "merges up &amp; reverts too", "claude/",
                     f"python3 {INSTALLED}/metrics.py add-reading"):
            self.assertIn(text, page)
        self.assertNotRegex(page, r'(src|href)="(https?:)?//')  # no external requests
        status = git(self.repo, "status", "--porcelain")
        self.assertNotIn(".scratch", status, "the throwaway page stays out of commits")

    def test_the_page_stays_inside_the_repository(self):
        code, _, _ = self.run_tool("compare", "--html", "../outside.html")
        self.assertEqual(code, 1)
        self.assertFalse((self.tmp / "outside.html").exists())


class Readings(Repo):
    def test_t7_two_readings_on_one_comparison_are_both_kept(self):
        ledger = self.repo / rm.LEDGER
        for who, text in (("maintainer", "Fewer rounds; maybe smaller tasks."),
                          ("an agent", "One revert in V1 is most of the change.")):
            code, _, err = self.run_tool("add-reading", "--about", "before", V1, "--author", who, "--text", text)
            self.assertEqual(code, 0, err)
            if who == "maintainer":
                first = ledger.read_text()
        self.assertTrue(ledger.read_text().startswith(first))  # appended, nothing rewritten
        readings = self.compare()["readings"]
        self.assertEqual([r["author"] for r in readings], ["maintainer", "an agent"])
        for r in readings:
            self.assertRegex(r["date"], r"^\d{4}-\d\d-\d\dT")
            self.assertEqual(r["about"], [rm.BEFORE, V1])
        head = git(self.repo, "rev-parse", "--short=12", "HEAD").strip()
        self.assertEqual({e["ref"] for e in rm.read(ledger)}, {head})  # what the numbers were computed at

    def test_a_reading_names_versions_that_exist(self):
        code, _, err = self.run_tool("add-reading", "--about", "ffffff", "--author", "x", "--text", "y")
        self.assertEqual(code, 1)
        self.assertIn("no version", err)

    def test_a_reading_is_a_short_note(self):
        code, _, _ = self.run_tool("add-reading", "--about", V1, "--author", "x", "--text", "y" * 1001)
        self.assertEqual(code, 1)


class StaysInTheRepository(Repo):
    def test_t9_reads_only_and_writes_only_inside_the_repository(self):
        git_log = self.log_git()
        outside = lambda: sorted(  # noqa: E731
            str(p) for p in self.tmp.rglob("*")
            if self.repo not in p.parents and p.parent != self.bin and p.suffix not in (".log", ".jsonl"))
        before = outside()
        for args in (("versions",), ("compare", "--html"),
                     ("add-reading", "--about", V2, "--author", "an agent", "--text", "noted"),
                     ("add-answer", "--pr", "7", "--stepped-in", "none", "--take-as-is", "yes")):
            code, _, err = self.run_tool(*args)
            self.assertEqual(code, 0, (args, err))
        self.assertEqual(outside(), before)
        gh_calls = [json.loads(line)["args"] for line in self.gh_log.read_text().splitlines()]
        self.assertTrue(gh_calls)
        for call in gh_calls:
            self.assertEqual(call[:2], ["pr", "list"], call)
        for call in map(json.loads, git_log.read_text().splitlines()):
            args = call[2:] if call[:1] == ["-C"] else call
            self.assertIn(args[0], READ_ONLY_GIT, call)
        changed = git(self.repo, "status", "--porcelain").split()
        self.assertEqual(changed, ["??", ".agents/metrics/"])  # the readings ledger, nothing else


class QuickAnswers(Repo):
    def answer(self, *args):
        code, out, err = self.run_tool("add-answer", *args)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def without_answers(self, data):
        return {k: v for k, v in data.items() if k not in ("answers", "as_of")}

    def test_t4_a_recorded_answer_sits_beside_its_task_and_nothing_else_changes(self):
        before = self.compare()
        self.assertEqual(before["answers"]["given"], [])
        self.answer("--pr", "7", "--stepped-in", "some", "--take-as-is", "with edits")
        after = self.compare()
        self.assertEqual(self.without_answers(after), self.without_answers(before))
        [given] = after["answers"]["given"]
        self.assertEqual((given["pr"], given["version"], given["stepped_in"], given["take_as_is"]),
                         (7, V2, "some", "with edits"))
        self.assertEqual(given["task"], {"pr": 7, "opened": "2026-03-02T00:00:00Z", "state": "merged",
                                         "review_rounds": 0, "hours_to_merge": 72.0, "corrections": 1})
        self.assertIn("#7", given["source"])
        self.assertIn("#7", self.cells(after, "agent_prs_opened")[V2]["source"])  # the same task's numbers

    def test_t4_with_no_answer_every_number_is_the_same_even_without_pull_requests(self):
        (self.bin / "gh").write_text(FAILING_GH.format(python=sys.executable))
        before = self.compare()
        self.answer("--pr", "7", "--take-as-is", "no")
        after = self.compare()
        self.assertEqual(self.without_answers(after), self.without_answers(before))
        [given] = after["answers"]["given"]
        self.assertIsNone(given["task"])
        self.assertEqual(given["version"], V2)  # recorded now, in the current version
        self.assertIn("gh auth login", given["source"])

    def test_t4_the_task_s_branch_ties_an_answer_to_its_pull_request(self):
        given = self.answer("--branch", "codex/dates", "--take-as-is", "No")
        self.assertEqual((given["branch"], given["take_as_is"]), ("codex/dates", "no"))
        self.assertNotIn("stepped_in", given)  # a question left unanswered isn't recorded
        git(self.repo, "switch", "-q", "-c", "claude/deploy")
        self.answer("--stepped-in", "a lot")  # the current branch
        first, second = self.compare()["answers"]["given"]
        self.assertEqual((first["pr"], first["version"], first["stepped_in"]), (4, V1, None))
        self.assertEqual((second["pr"], second["version"], second["branch"]), (7, V2, "claude/deploy"))
        self.assertEqual(first["task"]["review_rounds"], 2)

    def test_t4_only_the_fixed_choices_are_taken(self):
        for args in (("--pr", "7", "--stepped-in", "maybe"), ("--pr", "7", "--take-as-is", "sure"),
                     ("--pr", "7"), ("--pr", "7", "--stepped-in", "none", "--note", "y" * 1001)):
            code, _, err = self.run_tool("add-answer", *args)
            self.assertEqual(code, 1, args)
            self.assertIn("metrics:", err)
        self.assertFalse((self.repo / rm.LEDGER).exists())

    def test_t4_answers_show_with_the_versions_compared(self):
        self.answer("--pr", "7", "--stepped-in", "none", "--take-as-is", "yes")
        self.assertEqual(self.compare(V1)["answers"]["given"], [])
        self.assertEqual(len(self.compare(V2)["answers"]["given"]), 1)

    def test_x1_x5_answers_are_listed_one_by_one_never_counted(self):
        for number, choice in (("7", "none"), ("8", "none"), ("4", "a lot")):
            self.answer("--pr", number, "--stepped-in", choice)
        answers = self.compare()["answers"]
        self.assertEqual([(a["pr"], a["stepped_in"]) for a in answers["given"]],
                         [(7, "none"), (8, "none"), (4, "a lot")])  # as given, in the order given
        self.assertEqual(set(answers), {"about", "questions", "choices", "task_numbers", "given"})
        for kind, value in keys_and_strings(answers):
            if kind == "key":
                self.assertNotIn(value.lower(), FORBIDDEN_KEYS | {"author", "count", "total", "mean"})
        for entry in rm.read(self.repo / rm.LEDGER):
            self.assertNotIn("author", entry)  # who answered is never kept, so never compared

    def test_the_page_shows_each_answer_beside_its_task(self):
        self.answer("--pr", "4", "--stepped-in", "some", "--note", "renamed <it> twice")
        code, _, err = self.run_tool("compare", "--html")
        self.assertEqual(code, 0, err)
        page = (self.repo / rm.DEFAULT_PAGE).read_text()
        for text in ("Quick answers", "#4", "some", "renamed &lt;it&gt; twice", "2 review rounds",
                     "120 hours to merge", "2 corrections", rm.QUESTIONS["take_as_is"],
                     f"python3 {INSTALLED}/metrics.py add-answer"):
            self.assertIn(text, page)

    def test_the_retro_skill_asks_what_add_answer_records(self):
        retro = (ROOT / "skills" / "retro" / "SKILL.md").read_text()
        for q, text in rm.QUESTIONS.items():
            self.assertIn(f"{text} {' / '.join(rm.CHOICES[q])}", retro)
        self.assertIn(f"python3 {INSTALLED}/metrics.py add-answer", retro)
        cfg = json.loads((ROOT / "factory.json").read_text())
        self.assertLess({"retro", "metrics"}, set(cfg["skills"]))  # installed together, always


class NoVerdict(Repo):
    def setUp(self):
        super().setUp()
        self.run_tool("add-reading", "--about", V1, "--author", "maintainer", "--text", "fine")
        self.run_tool("add-answer", "--pr", "7", "--stepped-in", "a lot", "--take-as-is", "no")

    def test_t10_no_field_is_a_score_or_a_verdict_and_no_lines_of_code(self):
        for command in (("compare",), ("versions",)):
            _, out, _ = self.run_tool(*command)
            for kind, value in keys_and_strings(json.loads(out)):
                if kind == "key":
                    self.assertNotIn(value.lower(), FORBIDDEN_KEYS, command)
                    self.assertNotIn("line", value.lower(), command)
        for row in self.compare()["rows"]:
            self.assertNotIn(row["metric"], FORBIDDEN_KEYS)
            self.assertNotIn("line", row["metric"])
            for c in row["cells"]:
                self.assertNotIsInstance(c["value"], str)

    def test_t11_no_headline_and_one_version_alone_shows_all_its_numbers(self):
        data = self.compare(V1)
        self.assertEqual(set(data), {"about", "ledger", "as_of", "agent_rule", "versions", "rows", "answers",
                                     "readings"})
        self.assertEqual({r["metric"] for r in data["rows"]}, set(rm.DEFINITIONS))
        self.run_tool("compare", "--html")
        page = (self.repo / rm.DEFAULT_PAGE).read_text()
        for m in rm.DEFINITIONS:
            self.assertIn(m, page)
        self.assertNotIn("headline", page.lower())

    def test_t11_nothing_is_grouped_by_person(self):
        data = self.compare()
        self.assertEqual({r["group"] for r in data["rows"]}, set(rm.GROUPS))
        authors = [v for kind, v in keys_and_strings(data) if kind == "key" and v == "author"]
        self.assertEqual(len(authors), len(data["readings"]))  # only who wrote a reading
        self.assertNotIn("author", rm.PR_FIELDS)  # pull request authors are never read

    def test_t12_the_exit_code_is_the_same_whatever_the_numbers(self):
        prs = json.loads(self.prs_file.read_text())
        for p in prs:  # every agent pull request closed without merging
            p.update(state="CLOSED", mergedAt=None, mergeCommit=None)
        self.write_prs(prs)
        for args in (("compare",), ("compare", "--html"), ("versions",)):
            self.assertEqual(self.run_tool(*args)[0], 0, args)
        (self.bin / "gh").write_text(FAILING_GH.format(python=sys.executable))
        self.assertEqual(self.run_tool("compare")[0], 0)
        self.assertEqual(self.run_tool("compare", "no-such-version")[0], 1)  # only a usage error fails


class Installed(unittest.TestCase):
    def test_the_factory_installs_the_skill_with_its_script(self):
        files = factory.factory_files(ROOT, upstream=False)
        for base in factory.SKILL_DIRS:
            for f in ("SKILL.md", "metrics.py", "metrics_ledger.py"):
                self.assertIn(f"{base}/metrics/{f}", files)

    def test_after_a_real_apply_the_installed_copy_runs_on_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-q", "-b", "main")
            (repo / "README.md").write_text("a project\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "Start", when="2026-01-01T00:00:00+0000")
            done = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "factory.py"), "apply", str(repo),
                                   "--upstream", "no"], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "Apply the factory")
            for base in factory.SKILL_DIRS:
                out = subprocess.run([sys.executable, "-B", str(repo / base / "metrics" / "metrics.py"),
                                      "versions"], capture_output=True, text=True, cwd=repo)
                self.assertEqual(out.returncode, 0, out.stderr)
                applied = json.loads((repo / rm.MANIFEST).read_text())["version"]
                self.assertEqual([v["version"] for v in json.loads(out.stdout)], [rm.BEFORE, applied])


if __name__ == "__main__":
    unittest.main()
