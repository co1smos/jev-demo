import tempfile
import unittest
from pathlib import Path

from jev_demo.read_model import comparison
from jev_demo.run_store import RunStore


class ReadModelTests(unittest.TestCase):
    def test_comparison_derives_worked_metrics_from_three_persisted_results(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            ids = {}
            for method, ending in (
                ("jev", "109"),
                ("sma20_sma60", "106"),
                ("buy_and_hold", "104"),
            ):
                run_id = store.create({"trading_date": "2026-09-18", "method": method})
                store.complete(run_id, {
                    "method": method,
                    "source_digest": "a" * 64,
                    "starting_cash": "100",
                    "allocation_cap": "0.10",
                    "ending_equity": ending,
                    "fills": [
                        {"symbol": "AAPL", "side": "buy", "notional": "20", "execution_cost": "2"},
                        {"symbol": "AAPL", "side": "sell", "notional": str(20 + int(ending) - 100), "execution_cost": "2"},
                    ],
                    "fees": [{"kind": "regulatory", "amount": "1"}],
                    "equity_points": [
                        {"timestamp": "09:30", "equity": "100"},
                        {"timestamp": "09:31", "equity": "120"},
                        {"timestamp": "09:32", "equity": "90"},
                        {"timestamp": "09:33", "equity": ending},
                    ],
                    "execution_model_version": "execution-v1",
                    "fee_version": "fees-v1",
                })
                ids[method] = run_id

            result = comparison(store, ids["jev"])

        self.assertEqual(["jev", "sma20_sma60", "buy_and_hold"], [item["method"] for item in result["methods"]])
        jev = result["methods"][0]
        self.assertEqual("9", jev["net_profit"])
        self.assertEqual("0.09", jev["return"])
        self.assertEqual("30", jev["maximum_drawdown"])
        self.assertEqual("0.25", jev["maximum_drawdown_return"])
        self.assertEqual(2, jev["trade_count"])
        self.assertEqual("5", jev["total_costs"])
        self.assertEqual({"AAPL": "9"}, jev["per_stock_contribution"])
        self.assertEqual("5", jev["difference_from_buy_and_hold"]["net_profit"])
        self.assertEqual("0.05", jev["difference_from_buy_and_hold"]["return"])
        self.assertEqual(4, len(jev["equity_curve"]))
        self.assertEqual({
            "source_digest": "a" * 64,
            "starting_cash": "100",
            "allocation_cap": "0.10",
            "execution_model_version": "execution-v1",
            "fee_version": "fees-v1",
        }, result["shared_assumptions"])


if __name__ == "__main__":
    unittest.main()
