import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from jev_demo.__main__ import RunApplication, handler_for
from jev_demo.run_store import RunStore
from jev_demo.verification import verification_evidence


class VerificationTests(unittest.TestCase):
    def test_committed_evidence_captures_dashboard_and_csv_exports(self):
        evidence = json.loads(
            (Path(__file__).parents[1] / "docs/verification/2026-09-18.json").read_text()
        )

        self.assertEqual(evidence["runs"][1]["run_id"], evidence["dashboard"]["run_id"])
        self.assertEqual(evidence["date"], evidence["dashboard"]["trading_date"])
        self.assertEqual(
            ["jev", "sma20_sma60", "buy_and_hold"], evidence["dashboard"]["methods"]
        )
        self.assertEqual(64, len(evidence["dashboard"]["sha256"]))
        self.assertEqual(
            [run["run_id"] for run in evidence["runs"]],
            [export["run_id"] for export in evidence["csv_exports"]],
        )
        self.assertTrue(all(export["row_count"] > 0 for export in evidence["csv_exports"]))
        self.assertTrue(all(len(export["sha256"]) == 64 for export in evidence["csv_exports"]))

    def test_evidence_loads_completed_runs_and_csv_through_http(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            calls = 0

            def submit(run_id, request):
                nonlocal calls
                calls += 1
                group = f"group-{calls}"
                result = {
                    "method": "jev", "comparison_group_id": group,
                    "source_digest": "a" * 64, "starting_cash": "100000",
                    "allocation_cap": "0.10", "ending_equity": "100009",
                    "fills": [], "fees": [],
                    "equity_points": [{"timestamp": "09:30", "equity": "100000"}],
                    "execution_model_version": "next_minute_open_2bps_v1",
                    "fee_version": "us_equity_2026_v1",
                    "decisions": [{
                        "symbol": "AAPL", "minute": "2026-09-18T14:30:00Z",
                        "action": "HOLD", "probabilities": {"HOLD": 1}, "input": {},
                        "requested_model": "jev-1.13.0", "returned_model": "jev-1.13.0",
                        "input_version": "trend_momentum_v1",
                    }, {
                        "symbol": "MSFT", "minute": "2026-09-18T14:30:00Z",
                        "action": "ABSTAIN", "probabilities": {"ABSTAIN": 1}, "input": {},
                        "requested_model": "jev-1.13.0", "returned_model": None,
                        "input_version": "trend_momentum_v1", "error": "invalid_response",
                    }],
                    "actions": [], "orders": [],
                }
                store.append(run_id, "market_snapshot", {
                    "source_digest": "a" * 64, "reused": calls == 2,
                })
                store.complete(run_id, result)
                for method, profit in (("sma20_sma60", "6"), ("buy_and_hold", "4")):
                    child = store.create({**request, "method": method})
                    store.complete(child, {**result, "method": method,
                                           "ending_equity": str(100000 + int(profit)),
                                           "decisions": []})

            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                handler_for(RunApplication(store, submit), lambda: "2026-09-18"),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                run_ids = []
                for _ in range(2):
                    run_id = store.create({"trading_date": "2026-09-18", "method": "jev"})
                    submit(run_id, store.read(run_id)["request"])
                    run_ids.append(run_id)

                evidence = verification_evidence(base_url, *run_ids)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

        self.assertEqual(run_ids, [run["run_id"] for run in evidence["runs"]])
        self.assertEqual([False, True], [run["source_reused"] for run in evidence["runs"]])
        self.assertEqual("9", evidence["runs"][0]["final_metrics"][0]["net_profit"])
        self.assertEqual(run_ids[1], evidence["dashboard"]["run_id"])
        self.assertEqual("2026-09-18", evidence["dashboard"]["trading_date"])
        self.assertEqual(
            ["jev", "sma20_sma60", "buy_and_hold"], evidence["dashboard"]["methods"]
        )
        self.assertEqual(64, len(evidence["dashboard"]["sha256"]))
        self.assertTrue(all(evidence["checks"].values()))
        self.assertTrue(all(export["row_count"] == 2 for export in evidence["csv_exports"]))
        self.assertTrue(all(len(export["sha256"]) == 64 for export in evidence["csv_exports"]))


if __name__ == "__main__":
    unittest.main()
