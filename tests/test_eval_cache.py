"""The eval snapshot cache: filling one entry from many runs at once."""

import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))
import lib  # noqa: E402


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class CachedClone(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.origin = self.root / "origin"
        self.origin.mkdir()
        git(self.origin, "init", "--quiet")
        (self.origin / "README.md").write_text("hello\n")
        git(self.origin, "add", ".")
        git(self.origin, "-c", "user.name=t", "-c", "user.email=t@invalid",
            "commit", "--quiet", "-m", "first")
        self.entry = self.root / "cache" / "origin@abc"

    def usable(self, path):
        self.assertEqual((path / "README.md").read_text(), "hello\n")
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True)
        self.assertEqual(out.returncode, 0)

    def test_threads_asking_for_one_uncached_entry_all_get_a_checkout(self):
        n = 6
        barrier = threading.Barrier(n)
        got, errors = [], []

        def ask():
            barrier.wait()
            try:
                got.append(lib.cached_clone(str(self.origin), self.entry))
            except Exception as e:  # recorded, so the assertion names it
                errors.append(e)

        threads = [threading.Thread(target=ask) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(got, [self.entry] * n)
        self.usable(self.entry)
        self.assertEqual([p.name for p in self.entry.parent.iterdir()], [self.entry.name])

    def test_losing_the_rename_to_another_process_counts_as_success(self):
        real_sh = lib.sh

        def sh(cmd, *a, **kw):  # another process fills the entry while we clone
            if not self.entry.exists():
                real_sh(["git", "clone", "--quiet", str(self.origin), str(self.entry)])
            return real_sh(cmd, *a, **kw)

        with mock.patch.object(lib, "sh", sh):
            self.assertEqual(lib.cached_clone(str(self.origin), self.entry), self.entry)
        self.usable(self.entry)
        self.assertEqual([p.name for p in self.entry.parent.iterdir()], [self.entry.name])

    def test_a_failed_clone_leaves_no_entry(self):
        with self.assertRaises(RuntimeError):
            lib.cached_clone(str(self.root / "missing"), self.entry)
        self.assertFalse(self.entry.exists())
        self.assertEqual(list(self.entry.parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
