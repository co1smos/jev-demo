import sqlite3
import tempfile
import unittest
from pathlib import Path

from jev_demo.run_store import RunStore


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "runs.db"
        self.store = RunStore(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_run_lifecycle_is_append_only_and_completed_runs_are_immutable(self):
        request = {"date": "2026-09-18", "strategy": "trend_momentum_v1"}
        first = self.store.create(request)
        second = self.store.create(request)

        self.assertNotEqual(first, second)
        self.store.append(first, "decision", {"symbol": "AAPL", "action": "HOLD"})
        self.store.progress(first, 1, 3)
        self.store.complete(first, {"net_profit": "12.34"})

        run = self.store.read(first)
        self.assertEqual("completed", run["status"])
        self.assertEqual({"current": 1, "total": 3}, run["progress"])
        self.assertEqual({"net_profit": "12.34"}, run["result"])
        self.assertEqual(
            ["decision", "progress", "completed"],
            [record["kind"] for record in run["records"]],
        )
        self.assertTrue(all(record["timestamp"] for record in run["records"]))
        self.assertEqual([second, first], [item["id"] for item in self.store.list()])

        for operation in (
            lambda: self.store.append(first, "decision", {}),
            lambda: self.store.progress(first, 2, 3),
            lambda: self.store.complete(first, {}),
            lambda: self.store.fail(first, "late failure"),
        ):
            with self.assertRaises(ValueError):
                operation()

    def test_schema_initializes_and_failed_batch_rolls_back(self):
        run_id = self.store.create({"date": "2026-09-18"})

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.append(
                run_id,
                [
                    {"kind": "decision", "data": {"symbol": "AAPL"}},
                    {"kind": None, "data": {}},
                ],
            )

        reopened = RunStore(self.path)
        self.assertEqual([], reopened.read(run_id)["records"])
        reopened.fail(run_id, "provider unavailable")
        self.assertEqual("failed", reopened.read(run_id)["status"])


if __name__ == "__main__":
    unittest.main()
