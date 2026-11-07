"""The eval agents' allow-list: git -C forms, each naming its directory."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))
import lib  # noqa: E402


class GitDirs(unittest.TestCase):
    def setUp(self):
        self.tools = lib.with_git_dirs(lib.READ_ONLY_BASH + lib.SHIP_TOOLS, Path("/runs/T7-1"),
                                       ["/runs/T7-1-factory"])

    def test_the_repository_gets_every_allowed_git_command(self):
        self.assertIn("Bash(git -C /runs/T7-1 commit:*)", self.tools)
        self.assertIn("Bash(git -C /runs/T7-1 push:*)", self.tools)
        self.assertIn("Bash(git -C /runs/T7-1 status:*)", self.tools)

    def test_other_directories_get_only_read_only_git(self):
        for spelling in ("/runs/T7-1-factory", "../T7-1-factory"):
            self.assertIn(f"Bash(git -C {spelling} log:*)", self.tools)
            self.assertNotIn(f"Bash(git -C {spelling} commit:*)", self.tools)

    def test_no_wildcard_before_the_subcommand(self):
        for rule in self.tools:
            if rule.startswith("Bash(git -C "):
                self.assertNotIn("*", rule.split(":*")[0], rule)

    def test_the_bare_rules_are_kept(self):
        self.assertIn("Bash(git commit:*)", self.tools)
        self.assertIn("Bash(gh:*)", self.tools)


if __name__ == "__main__":
    unittest.main()
