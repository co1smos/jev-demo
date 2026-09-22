import tempfile
import unittest
from pathlib import Path

from jev_demo.run_store import RunStore
from jev_demo.verification import verification_evidence


class VerificationTests(unittest.TestCase):
    def test_evidence_proves_distinct_cached_run_and_records_versions_metrics_and_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            run_ids = []
            for reused in (False, True):
                group = f"group-{len(run_ids) + 1}"
                for method, profit in (("jev", "9"), ("sma20_sma60", "6"), ("buy_and_hold", "4")):
                    run_id = store.create({"trading_date": "2026-09-18", "method": method})
                    if method == "jev":
                        run_ids.append(run_id)
                        store.append(run_id, "market_snapshot", {
                            "source_digest": "a" * 64, "reused": reused,
                        })
                    store.complete(run_id, {
                        "method": method,
                        "comparison_group_id": group,
                        "source_digest": "a" * 64,
                        "starting_cash": "100000",
                        "allocation_cap": "0.10",
                        "ending_equity": str(100000 + int(profit)),
                        "fills": [],
                        "fees": [],
                        "equity_points": [{"timestamp": "09:30", "equity": "100000"}],
                        "execution_model_version": "next_minute_open_2bps_v1",
                        "fee_version": "us_equity_2026_v1",
                        "decisions": [{
                            "requested_model": "jev-1.13.0",
                            "returned_model": "jev-1.13.0",
                            "input_version": "trend_momentum_v1",
                        }],
                    })

            evidence = verification_evidence(store, *run_ids, dashboard_rendered=True)

        self.assertEqual(run_ids, [run["run_id"] for run in evidence["runs"]])
        self.assertEqual([False, True], [run["source_reused"] for run in evidence["runs"]])
        self.assertEqual("jev-1.13.0", evidence["requested_jev_model"])
        self.assertEqual("jev-1.13.0", evidence["returned_jev_model"])
        self.assertEqual("trend_momentum_v1", evidence["strategy_version"])
        self.assertEqual("9", evidence["runs"][0]["final_metrics"][0]["net_profit"])
        self.assertTrue(all(evidence["checks"].values()))


if __name__ == "__main__":
    unittest.main()
