"""The privacy scan, through its command line: what it catches and lets pass."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCAN = Path(__file__).resolve().parent.parent / "tools" / "privacy_scan.py"

# Planted values are assembled at runtime so this file passes the scan itself.
EMAIL = "jane.doe" + "@" + "gmail.com"
PHONE = "+1 415" + "-555-0132"
HOME = "/" + "home/jdoe"


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "t")
        self.git("config", "user.email", "t@example.com")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.path, check=True, capture_output=True)

    def write(self, name, text):
        p = self.path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def scan(self):
        out = subprocess.run([sys.executable, "-I", str(SCAN), str(self.path)],
                             capture_output=True, text=True)
        return out.returncode, out.stdout


class PrivacyScan(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.tmp.cleanup)

    def test_clean_repository_passes(self):
        self.repo.write("README.md", "Write to dev@example.com or see /home/<user>/project.\n")
        code, out = self.repo.scan()
        self.assertEqual(code, 0, out)

    def test_says_when_private_terms_are_not_checked(self):
        self.repo.write("README.md", "hello\n")
        code, out = self.repo.scan()
        self.assertEqual(code, 0, out)
        self.assertIn("private terms not checked", out)

    def test_reports_contact_details_and_home_paths_with_their_location(self):
        self.repo.write("docs/a.md", f"intro\nmail {EMAIL}\ncall {PHONE}\n")
        self.repo.write("b.py", f"ROOT = '{HOME}/projects'\n")
        code, out = self.repo.scan()
        self.assertEqual(code, 1)
        self.assertIn(f"docs/a.md:2: email: {EMAIL}", out)
        self.assertIn("docs/a.md:3: phone", out)
        self.assertIn(f"b.py:1: home path: {HOME}", out)

    def test_private_term_is_caught_but_never_printed(self):
        self.repo.write(".privacy-terms", "# local list\nAcmeCorp\n")
        self.repo.write("notes.md", "Lessons from my time at acmecorp.\n")
        code, out = self.repo.scan()
        self.assertEqual(code, 1)
        self.assertIn("notes.md:1: private term: #1", out)
        self.assertNotIn("acmecorp", out.lower())

    def test_private_term_in_a_commit_message_is_caught(self):
        self.repo.write(".gitignore", ".privacy-terms\n")
        self.repo.write("a.md", "fine\n")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-q", "-m", "Port the AcmeCorp deploy notes")
        self.repo.write(".privacy-terms", "AcmeCorp\n")
        code, out = self.repo.scan()
        self.assertEqual(code, 1)
        self.assertIn("commit ", out)

    def test_ignored_files_are_not_scanned(self):
        self.repo.write(".gitignore", ".scratch/\n")
        self.repo.write(".scratch/draft.md", EMAIL + "\n")
        code, out = self.repo.scan()
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
