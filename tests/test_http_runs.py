import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jev_demo.__main__ import RunApplication, handler_for, simulation_identity
from jev_demo.historical_data import AlpacaHistoricalData
from jev_demo.run_store import RunStore


class HttpRunTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = RunStore(Path(self.directory.name) / "runs.db")
        self.started = []
        self.workers = []
        self.release = threading.Event()
        self.latest_date = lambda: "2026-09-18"

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
            ("127.0.0.1", 0),
            handler_for(RunApplication(self.store, submit), lambda: self.latest_date()),
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
        status, created = self.request(
            "/api/runs", "POST", {"trading_date": "2026-09-18"},
            {"Idempotency-Key": "browser-submit-1"},
        )
        duplicate_status, duplicate = self.request(
            "/api/runs", "POST", {"trading_date": "2026-09-18"},
            {"Idempotency-Key": "browser-submit-2"},
        )

        self.assertEqual(202, status)
        self.assertEqual(200, duplicate_status)
        self.assertEqual(created["id"], duplicate["id"])
        self.assertTrue(duplicate["reused"])
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

        completed_status, completed_duplicate = self.request(
            "/api/runs", "POST", {"trading_date": "2026-09-18"},
            {"Idempotency-Key": "browser-submit-3"},
        )
        self.assertEqual(200, completed_status)
        self.assertEqual(created["id"], completed_duplicate["id"])
        self.assertTrue(completed_duplicate["reused"])
        self.assertEqual(1, len(self.started))

    def test_failed_equivalent_run_can_be_retried(self):
        submitted = []
        application = RunApplication(self.store, lambda run_id, request: submitted.append(run_id))
        failed, _ = application.create(
            {"trading_date": "2026-09-17"}, "failed-attempt"
        )
        self.store.fail(failed["id"], "provider unavailable")

        retried, created = application.create(
            {"trading_date": "2026-09-17"}, "explicit-retry"
        )

        self.assertTrue(created)
        self.assertNotEqual(failed["id"], retried["id"])
        self.assertEqual(2, len(submitted))

    def test_changed_versioned_assumption_creates_a_new_run(self):
        _, first = self.request(
            "/api/runs", "POST", {"trading_date": "2026-09-18"},
            {"Idempotency-Key": "current-fees"},
        )
        with patch("jev_demo.__main__.FEE_MODEL_VERSION", "us_equity_2027_v1"):
            status, changed = self.request(
                "/api/runs", "POST", {"trading_date": "2026-09-18"},
                {"Idempotency-Key": "changed-fees"},
            )

        self.assertEqual(202, status)
        self.assertNotEqual(first["id"], changed["id"])
        self.assertEqual(2, len(self.started))

    def test_simulation_identity_covers_ordered_inputs_and_versions(self):
        identity = simulation_identity("2026-09-18")

        self.assertEqual(
            {
                "trading_date": "2026-09-18",
                "symbols": ["AAPL", "MSFT", "NVDA"],
                "strategy_version": "trend_momentum_v1",
                "requested_model": "jev-1.13.0",
                "question_version": "stock_action_v1",
                "execution_model_version": "next_minute_open_2bps_v1",
                "fee_version": "us_equity_2026_v1",
            },
            identity,
        )
        self.assertNotEqual(identity, simulation_identity("2026-09-17"))

    def test_invalid_create_is_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/runs", "POST", {"trading_date": "not-a-date"})
        self.assertEqual(400, caught.exception.code)

    def test_page_exposes_accessible_run_workflow_without_api_key_fields(self):
        with urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode()

        self.assertIn("Historical paper trading", page)
        self.assertIn('<label for="trading-date">Trading date</label>', page)
        self.assertIn('type="date" id="trading-date"', page)
        self.assertIn('value="2026-09-18"', page)
        self.assertIn('id="run-status" role="status"', page)
        self.assertIn('id="completed-runs"', page)
        self.assertIn('id="comparison-summary"', page)
        self.assertIn('<caption>Method comparison</caption>', page)
        self.assertIn('<details id="equity-data">', page)
        self.assertIn('id="result-status" role="status"', page)
        self.assertIn('<caption>JEV fills</caption>', page)
        self.assertIn('<caption>JEV fees</caption>', page)
        self.assertIn('<caption>JEV ending positions</caption>', page)
        self.assertIn('aria-busy', page)
        self.assertIn('Showing the last loaded data.', page)
        self.assertIn('"/api/runs"', page)
        self.assertIn("Reused existing run", page)
        self.assertIn("if(run.reused&&run.status===\"completed\")", page)
        self.assertNotIn('type="password"', page)
        self.assertNotIn("API key", page)

    def test_page_initially_shows_durable_parent_run_history_and_context(self):
        completed = self.store.create({"trading_date": "2026-09-16", "method": "jev"})
        self.store.complete(completed, {"method": "jev"})
        failed = self.store.create({"trading_date": "2026-09-17", "method": "jev"})
        self.store.fail(failed, "provider unavailable")
        running = self.store.create({"trading_date": "2026-09-18", "method": "jev"})
        self.store.progress(running, 1, 2)
        internal = self.store.create({"trading_date": "2026-09-18", "method": "buy_and_hold"})
        self.store.complete(internal, {})

        with urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode()

        self.assertIn("Run history", page)
        self.assertIn(f'href="/?run={completed}"', page)
        self.assertIn("2026-09-16", page)
        self.assertIn("2026-09-17", page)
        self.assertIn("provider unavailable", page)
        self.assertIn("2026-09-18", page)
        self.assertIn("Progress: 1 of 2", page)
        self.assertIn("Created", page)
        self.assertIn("Updated", page)
        self.assertNotIn(internal, page)

    def test_empty_history_explains_the_separate_verification_database(self):
        with urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode()

        self.assertIn(
            "Verification evidence used a separate temporary database and was not imported",
            page,
        )

    def test_page_ignores_stale_selection_responses_and_retries_progress(self):
        with urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode()

        self.assertIn("if(id!==selectedRun)return", page)
        self.assertIn("Last known progress", page)
        self.assertIn("setTimeout(()=>poll(id,reused),1000)", page)

    def test_completed_run_audit_json_csv_and_page_filters(self):
        minute = "2026-09-18T14:30:00Z"
        decision = {
            "symbol": "AAPL", "minute": minute, "action": "BUY",
            "probabilities": {"BUY": 0.75, "HOLD": 0.15, "SELL": 0.05, "ABSTAIN": 0.05},
            "input": {"sma20": 101.5, "minutes_remaining": 330},
            "input_version": "trend_momentum_v1", "question_version": "stock_action_v1",
            "requested_model": "jev-1.13.0", "returned_model": "jev-1.13.0",
        }
        run_id = self.store.create({"trading_date": "2026-09-18", "method": "jev"})
        self.store.complete(run_id, {
            "decisions": [decision],
            "actions": [{"symbol": "AAPL", "minute": minute, "action": "BUY",
                         "available": True, "explanation": "open_to_10_percent_target"}],
            "orders": [], "fills": [],
        })

        _, audit = self.request(
            f"/api/runs/{run_id}/audit?symbol=AAPL&action=BUY&minute={minute}"
        )
        with urlopen(self.base_url + f"/api/runs/{run_id}/audit.csv?symbol=AAPL", timeout=2) as response:
            csv_text = response.read().decode()
            content_type = response.headers["Content-Type"]
        with urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode()

        self.assertEqual("open_to_10_percent_target", audit["decisions"][0]["explanation"])
        self.assertIn("text/csv", content_type)
        self.assertIn("buy_probability", csv_text)
        self.assertIn("0.75", csv_text)
        self.assertNotIn("Authorization", csv_text)
        self.assertIn('id="audit-symbol"', page)
        self.assertIn('id="audit-action"', page)
        self.assertIn('id="audit-minute"', page)
        self.assertIn("Download CSV", page)

    def test_comparison_endpoint_returns_all_persisted_methods(self):
        ids = {}
        for method in ("jev", "sma20_sma60", "buy_and_hold"):
            run_id = self.store.create({"trading_date": "2026-09-18", "method": method})
            self.store.complete(run_id, {
                "method": method,
                "comparison_group_id": "comparison-1",
                "source_digest": "a" * 64,
                "starting_cash": "100000",
                "allocation_cap": "0.10",
                "ending_equity": "100010",
                "fills": [],
                "fees": [],
                "positions": [],
                "equity_points": [{"timestamp": "09:30", "equity": "100010"}],
                "execution_model_version": "execution-v1",
                "fee_version": "fees-v1",
            })
            ids[method] = run_id

        status, result = self.request(f"/api/runs/{ids['jev']}/comparison")
        with urlopen(self.base_url + f"/?run={ids['jev']}", timeout=2) as response:
            page = response.read().decode()

        self.assertEqual(200, status)
        self.assertEqual(
            ["jev", "sma20_sma60", "buy_and_hold"],
            [method["method"] for method in result["methods"]],
        )
        self.assertIn(f'data-run-id="{ids["jev"]}"', page)
        self.assertIn("<td>jev</td>", page)
        self.assertIn("if(summary.dataset.runId)selectRun(summary.dataset.runId)", page)

    def test_page_defaults_to_latest_completed_exchange_session(self):
        cases = (
            (
                datetime(2026, 9, 21, 21, tzinfo=timezone.utc),
                [
                    {"date": "2026-09-18", "open": "09:30", "close": "16:00"},
                    {"date": "2026-09-21", "open": "09:30", "close": "16:00"},
                ],
                "2026-09-21",
            ),
            (
                datetime(2026, 9, 7, 21, tzinfo=timezone.utc),
                [{"date": "2026-09-04", "open": "09:30", "close": "16:00"}],
                "2026-09-04",
            ),
        )
        for now, calendar, expected in cases:
            with self.subTest(now=now):
                data = AlpacaHistoricalData(
                    "key",
                    "secret",
                    self.directory.name,
                    request=lambda request, calendar=calendar: json.dumps(calendar).encode(),
                    now=lambda now=now: now,
                )
                self.latest_date = data.latest_completed_date

                with urlopen(self.base_url + "/", timeout=2) as response:
                    page = response.read().decode()

                self.assertIn(f'value="{expected}"', page)

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

    def test_history_survives_store_application_and_http_server_restart(self):
        path = Path(self.directory.name) / "restart.db"
        store = RunStore(path)
        run_id = store.create({"trading_date": "2026-09-15", "method": "jev"})
        store.complete(run_id, {"method": "jev"})

        def page_after_restart():
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                handler_for(RunApplication(RunStore(path), lambda *_: None), self.latest_date),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=2) as response:
                    return response.read().decode()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

        self.assertIn(f'href="/?run={run_id}"', page_after_restart())
        self.assertIn(f'href="/?run={run_id}"', page_after_restart())


if __name__ == "__main__":
    unittest.main()
