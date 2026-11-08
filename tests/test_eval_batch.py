"""Eval batch folders: batches started in the same second never share one."""

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evals"))
import lib  # noqa: E402

STAMP = "20261106-120000-T1"


class ClaimBatch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = mock.patch.dict(os.environ, {"FACTORY_EVAL_DIR": str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def owned(self, name):
        self.assertTrue((self.root / "results" / name).is_dir())
        self.assertTrue((self.root / "runs" / name).is_dir())

    def test_two_batches_with_one_stamp_get_separate_folders(self):
        first, second = lib.claim_batch(STAMP), lib.claim_batch(STAMP)
        self.assertEqual(first, STAMP)
        self.assertNotEqual(first, second)
        self.owned(first)
        self.owned(second)

    def test_batches_claiming_at_once_all_get_their_own(self):
        n = 6
        barrier = threading.Barrier(n)
        got, errors = [], []

        def claim():
            barrier.wait()
            try:
                got.append(lib.claim_batch(STAMP))
            except Exception as e:  # recorded, so the assertion names it
                errors.append(e)

        threads = [threading.Thread(target=claim) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(got)), n)
        for name in got:
            self.owned(name)
        self.assertEqual(sorted(p.name for p in (self.root / "results").iterdir()), sorted(got))

    def test_a_runs_folder_left_by_an_older_batch_is_not_reused(self):
        (self.root / "runs" / STAMP).mkdir(parents=True)
        name = lib.claim_batch(STAMP)
        self.assertNotEqual(name, STAMP)
        self.owned(name)
        self.assertFalse((self.root / "results" / STAMP).exists())


if __name__ == "__main__":
    unittest.main()
