"""The factory helper, through its command line: apply, update, local edits kept."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "factory.py"


class Factory:
    """A small factory on disk that tests can change between applies."""

    def __init__(self, root: Path):
        self.root = root
        self.write("factory.json", json.dumps({
            "skills": ["alpha", "beta"],
            "upstream_skills": ["send-lessons"],
            "settings": {"projects": "docs/projects/", "upstream": "no"},
        }))
        self.write("skills/alpha/SKILL.md", "alpha v1\n")
        self.write("skills/beta/SKILL.md", "beta v1\n")
        self.write("skills/send-lessons/SKILL.md", "send v1\n")
        self.write("rules-block.md", "## Software factory\n\n- Check intent first.\n")

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def remove(self, rel):
        (self.root / rel).unlink()


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.factory = Factory(Path(tmp.name) / "factory")
        self.repo = Path(tmp.name) / "repo"
        self.repo.mkdir()

    def run_tool(self, *args):
        out = subprocess.run(
            [sys.executable, "-I", str(TOOL), *args, str(self.repo), "--factory", str(self.factory.root)],
            capture_output=True, text=True)
        return out.returncode, out.stdout + out.stderr

    def apply(self, *flags):
        code, out = self.run_tool("apply", *flags)
        self.assertEqual(code, 0, out)
        return out

    def read(self, rel):
        return (self.repo / rel).read_text()

    def edit(self, rel, text):
        (self.repo / rel).write_text(text)


class FirstApply(Case):
    def test_asks_for_the_upstream_answer_before_installing_anything(self):
        code, out = self.run_tool("apply")
        self.assertEqual(code, 1)
        self.assertIn("--upstream", out)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_keeps_existing_rules_and_adds_one_marked_block(self):
        self.edit("AGENTS.md", "# Our rules\n\nNever edit legacy/.\n")
        self.apply("--upstream", "no")
        rules = self.read("AGENTS.md")
        self.assertTrue(rules.startswith("# Our rules\n\nNever edit legacy/.\n"))
        self.assertEqual(rules.count("<!-- soft-factorio:begin -->"), 1)
        self.assertIn("- Check intent first.", rules)

    def test_skills_are_readable_by_each_agent_tool(self):
        self.apply("--upstream", "no")
        for base in (".agents/skills", ".claude/skills"):
            self.assertEqual(self.read(f"{base}/alpha/SKILL.md"), "alpha v1\n")

    def test_answer_no_installs_no_upstream_skill_and_is_recorded(self):
        self.apply("--upstream", "no")
        self.assertFalse((self.repo / ".agents/skills/send-lessons").exists())
        self.assertIn("| `upstream` | `no` |", self.read("AGENTS.md"))

    def test_answer_yes_installs_the_upstream_skill_and_is_recorded(self):
        self.apply("--upstream", "yes")
        self.assertEqual(self.read(".agents/skills/send-lessons/SKILL.md"), "send v1\n")
        self.assertIn("| `upstream` | `yes` |", self.read("AGENTS.md"))

    def test_the_repositorys_own_skill_of_the_same_name_wins(self):
        (self.repo / ".claude/skills/beta").mkdir(parents=True)
        self.edit(".claude/skills/beta/SKILL.md", "our own beta\n")
        out = self.apply("--upstream", "no")
        self.assertEqual(self.read(".claude/skills/beta/SKILL.md"), "our own beta\n")
        self.assertFalse((self.repo / ".agents/skills/beta").exists())
        self.assertIn("own 'beta' skill wins", out)


class Update(Case):
    def setUp(self):
        super().setUp()
        self.edit("AGENTS.md", "# Our rules\n")
        self.apply("--upstream", "no")

    def test_reapplying_an_unchanged_factory_changes_nothing(self):
        before = {p: p.read_bytes() for p in self.repo.rglob("*") if p.is_file()
                  and not p.name == "manifest.json"}
        self.apply()
        after = {p: p.read_bytes() for p in self.repo.rglob("*") if p.is_file()
                 and not p.name == "manifest.json"}
        self.assertEqual(before, after)

    def test_brings_a_factory_change_to_an_untouched_file(self):
        self.factory.write("skills/alpha/SKILL.md", "alpha v2\n")
        out = self.apply()
        self.assertEqual(self.read(".agents/skills/alpha/SKILL.md"), "alpha v2\n")
        self.assertIn("updated from the factory", out)

    def test_keeps_a_local_edit_and_reports_it(self):
        self.edit(".agents/skills/alpha/SKILL.md", "alpha, our way\n")
        self.factory.write("skills/beta/SKILL.md", "beta v2\n")
        out = self.apply()
        self.assertEqual(self.read(".agents/skills/alpha/SKILL.md"), "alpha, our way\n")
        self.assertEqual(self.read(".agents/skills/beta/SKILL.md"), "beta v2\n")
        self.assertIn("kept: local edit", out)
        self.assertIn(".agents/skills/alpha/SKILL.md", out)

    def test_a_local_edit_survives_later_updates_too(self):
        self.edit(".agents/skills/alpha/SKILL.md", "alpha, our way\n")
        self.apply()
        self.factory.write("skills/beta/SKILL.md", "beta v2\n")
        self.apply()
        self.assertEqual(self.read(".agents/skills/alpha/SKILL.md"), "alpha, our way\n")

    def test_an_edit_on_both_sides_stops_and_changes_nothing(self):
        self.edit(".agents/skills/alpha/SKILL.md", "alpha, our way\n")
        self.factory.write("skills/alpha/SKILL.md", "alpha v2\n")
        self.factory.write("skills/beta/SKILL.md", "beta v2\n")
        code, out = self.run_tool("apply")
        self.assertEqual(code, 2)
        self.assertIn("CONFLICT", out)
        self.assertIn(".agents/skills/alpha/SKILL.md", out)
        self.assertEqual(self.read(".agents/skills/alpha/SKILL.md"), "alpha, our way\n")
        self.assertEqual(self.read(".agents/skills/beta/SKILL.md"), "beta v1\n")

    def test_a_conflict_resolved_ours_keeps_the_local_edit(self):
        self.edit(".agents/skills/alpha/SKILL.md", "alpha, our way\n")
        self.factory.write("skills/alpha/SKILL.md", "alpha v2\n")
        self.apply("--resolve", ".agents/skills/alpha/SKILL.md=ours")
        self.assertEqual(self.read(".agents/skills/alpha/SKILL.md"), "alpha, our way\n")
        self.assertEqual(self.read(".claude/skills/alpha/SKILL.md"), "alpha v2\n")

    def test_a_conflict_resolved_theirs_takes_the_factory_version(self):
        self.edit(".agents/skills/alpha/SKILL.md", "alpha, our way\n")
        self.factory.write("skills/alpha/SKILL.md", "alpha v2\n")
        self.apply("--resolve", ".agents/skills/alpha/SKILL.md=theirs")
        self.assertEqual(self.read(".agents/skills/alpha/SKILL.md"), "alpha v2\n")

    def test_updates_the_rules_block_without_touching_the_repositorys_rules(self):
        self.edit("AGENTS.md", self.read("AGENTS.md").replace("# Our rules\n", "# Our rules\n\nUse tabs.\n"))
        self.factory.write("rules-block.md", "## Software factory\n\n- Check intent first.\n- Ship PRs.\n")
        self.apply()
        rules = self.read("AGENTS.md")
        self.assertIn("Use tabs.", rules)
        self.assertIn("- Ship PRs.", rules)
        self.assertEqual(rules.count("<!-- soft-factorio:begin -->"), 1)

    def test_a_local_edit_inside_the_block_meets_a_factory_change_as_a_conflict(self):
        self.edit("AGENTS.md", self.read("AGENTS.md").replace("- Check intent first.", "- Check intent first, always."))
        self.factory.write("rules-block.md", "## Software factory\n\n- Check intent first.\n- Ship PRs.\n")
        code, out = self.run_tool("apply")
        self.assertEqual(code, 2)
        self.assertIn("AGENTS.md#soft-factorio", out)

    def test_keeps_the_repositorys_settings(self):
        self.edit("AGENTS.md", self.read("AGENTS.md").replace("`docs/projects/`", "`plans/`"))
        self.apply()
        self.assertIn("| `projects` | `plans/` |", self.read("AGENTS.md"))
        self.assertIn("| `upstream` | `no` |", self.read("AGENTS.md"))

    def test_removes_a_file_the_factory_dropped_unless_edited_locally(self):
        self.factory.write("skills/alpha/extra.md", "extra\n")
        self.factory.write("skills/beta/extra.md", "extra\n")
        self.apply()
        self.edit(".agents/skills/beta/extra.md", "our notes\n")
        self.factory.remove("skills/alpha/extra.md")
        self.factory.remove("skills/beta/extra.md")
        self.apply()
        self.assertFalse((self.repo / ".agents/skills/alpha/extra.md").exists())
        self.assertEqual(self.read(".agents/skills/beta/extra.md"), "our notes\n")

    def factory_commit(self, message):
        def git(*a):
            subprocess.run(["git", "-C", str(self.factory.root), "-c", "user.name=t",
                            "-c", "user.email=t@example.com", *a], check=True, capture_output=True)
        if not (self.factory.root / ".git").exists():
            git("init", "-q")
        git("add", "-A")
        git("commit", "-qm", message)

    def test_an_update_lists_the_factory_changes_since_the_installed_commit(self):
        self.factory_commit("Start the factory")
        self.apply()
        self.factory.write("skills/alpha/SKILL.md", "alpha v2\n")
        self.factory_commit("Teach alpha to ask first")
        out = self.apply()
        self.assertIn("Teach alpha to ask first", out)
        self.assertNotIn("Start the factory", out)

    def test_records_an_uncommitted_factory_as_modified(self):
        self.factory_commit("v")
        self.apply()
        clean = json.loads(self.read(".agents/factory/manifest.json"))["version"]
        self.factory.write("skills/alpha/SKILL.md", "alpha draft\n")
        self.apply()
        dirty = json.loads(self.read(".agents/factory/manifest.json"))["version"]
        self.assertFalse(clean.endswith("-modified"))
        self.assertEqual(dirty, clean + "-modified")

    def test_plan_changes_nothing(self):
        self.factory.write("skills/alpha/SKILL.md", "alpha v2\n")
        code, out = self.run_tool("plan")
        self.assertEqual(code, 0, out)
        self.assertIn("plan only", out)
        self.assertEqual(self.read(".agents/skills/alpha/SKILL.md"), "alpha v1\n")


if __name__ == "__main__":
    unittest.main()
