import json
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jev_demo.__main__ import RunApplication, handler_for
from jev_demo.run_store import RunStore


class HttpRunTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = RunStore(Path(self.directory.name) / "runs.db")
        self.started = []
        self.workers = []
        self.release = threading.Event()

        def submit(run_id, request):
            self.started.append((run_id, request))

            def work():
                self.store.progress(run_id, 1, 2)
                self.release.wait(2)
                self.store.progress(run_id, 2, 2)
                self.store.complete(run_id, {"net_pnl": "12.34"})

            worker = threading.Thread(target=work, daemon=True)
            self.workers.append(worker)
            worker.start()

        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), handler_for(RunApplication(self.store, submit))
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        for worker in self.workers:
            worker.join(2)
        self.directory.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        request = Request(
            self.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_create_duplicate_progress_list_and_result(self):
        headers = {"Idempotency-Key": "browser-submit-1"}
        status, created = self.request(
            "/api/runs", "POST", {"trading_date": "2026-09-18"}, headers
        )
        duplicate_status, duplicate = self.request(
            "/api/runs", "POST", {"trading_date": "2026-09-18"}, headers
        )

        self.assertEqual(202, status)
        self.assertEqual(200, duplicate_status)
        self.assertEqual(created["id"], duplicate["id"])
        self.assertEqual(1, len(self.started))

        for _ in range(100):
            _, progress = self.request(f"/api/runs/{created['id']}")
            if progress["progress"]["current"] == 1:
                break
            time.sleep(0.01)
        self.assertEqual("running", progress["status"])
        self.assertEqual({"current": 1, "total": 2}, progress["progress"])
        result_status, pending = self.request(f"/api/runs/{created['id']}/result")
        self.assertEqual(202, result_status)
        self.assertEqual("running", pending["status"])

        _, runs = self.request("/api/runs")
        self.assertEqual([created["id"]], [run["id"] for run in runs])

        self.release.set()
        for _ in range(100):
            _, completed = self.request(f"/api/runs/{created['id']}/result")
            if completed["status"] == "completed":
                break
            time.sleep(0.01)
        self.assertEqual({"net_pnl": "12.34"}, completed["result"])

    def test_invalid_create_is_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/runs", "POST", {"trading_date": "not-a-date"})
        self.assertEqual(400, caught.exception.code)

    def test_page_exposes_accessible_run_workflow_without_api_key_fields(self):
        with urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode()

        latest = date.today() - timedelta(days=1)
        while latest.weekday() > 4:
            latest -= timedelta(days=1)
        self.assertIn("Historical paper trading", page)
        self.assertIn('<label for="trading-date">Trading date</label>', page)
        self.assertIn('type="date" id="trading-date"', page)
        self.assertIn(f'value="{latest.isoformat()}"', page)
        self.assertIn('id="run-status" role="status"', page)
        self.assertIn('id="completed-runs"', page)
        self.assertIn('"/api/runs"', page)
        self.assertNotIn('type="password"', page)
        self.assertNotIn("API key", page)

    def test_restart_preserves_completed_and_fails_interrupted_runs(self):
        completed = self.store.create({"trading_date": "2026-09-17", "method": "buy_and_hold"})
        self.store.complete(completed, {"net_pnl": "1.00"})
        interrupted = self.store.create({"trading_date": "2026-09-18", "method": "buy_and_hold"})

        reopened = RunStore(Path(self.directory.name) / "runs.db")
        RunApplication(reopened, lambda run_id, request: None)

        self.assertEqual("completed", reopened.read(completed)["status"])
        _, failed = self.request(f"/api/runs/{interrupted}/result")
        self.assertEqual("failed", failed["status"])
        self.assertEqual("web process restarted before the run completed", failed["error"])


if __name__ == "__main__":
    unittest.main()
