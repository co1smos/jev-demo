import csv
import io
import tempfile
import unittest
from pathlib import Path

from jev_demo.audit import audit_csv, read_audit
from jev_demo.run_store import RunStore


class AuditTests(unittest.TestCase):
    def test_completed_jev_audit_filters_links_and_exports_exact_values(self):
        decision = {
            "symbol": "AAPL",
            "minute": "2026-09-18T14:30:00Z",
            "action": "BUY",
            "probabilities": {"BUY": 0.7, "HOLD": 0.2, "SELL": 0.1, "ABSTAIN": 0.0},
            "input": {"sma20": 101.25, "trend": "above", "minutes_remaining": 330},
            "input_version": "trend_momentum_v1",
            "question_version": "stock_action_v1",
            "requested_model": "jev-1.13.0",
            "returned_model": "jev-1.13.0",
        }
        order = {
            "id": "order-1", "symbol": "AAPL", "side": "buy", "quantity": 98,
            "submitted_at": decision["minute"], "fill_at": "2026-09-18T14:31:00Z",
            "reason": "jev",
        }
        fill = {
            "id": "fill-1", "order_id": "order-1", "symbol": "AAPL", "side": "buy",
            "quantity": 98, "timestamp": order["fill_at"], "price": "101.27025",
        }
        result = {
            "decisions": [decision, {**decision, "symbol": "MSFT", "action": "HOLD"}],
            "actions": [
                {"symbol": "AAPL", "minute": decision["minute"], "action": "BUY",
                 "available": True, "explanation": "open_to_10_percent_target"},
                {"symbol": "MSFT", "minute": decision["minute"], "action": "HOLD",
                 "available": True, "explanation": "no_change"},
            ],
            "orders": [order],
            "fills": [fill],
        }

        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            run_id = store.create({"trading_date": "2026-09-18", "method": "jev"})
            store.complete(run_id, result)
            audit = read_audit(store, run_id, symbol="AAPL", action="BUY",
                               minute=decision["minute"])
            exported = audit_csv(audit)

        self.assertEqual([{
            **decision,
            "explanation": "open_to_10_percent_target",
            "error": None,
            "orders": [order],
            "fills": [fill],
        }], audit["decisions"])
        rows = list(csv.DictReader(io.StringIO(exported)))
        self.assertEqual("0.7", rows[0]["buy_probability"])
        self.assertEqual("101.25", rows[0]["sma20"])
        self.assertEqual("order-1", rows[0]["order_ids"])
        self.assertEqual("fill-1", rows[0]["fill_ids"])
        self.assertFalse(any("key" in heading.lower() or "authorization" in heading.lower()
                             for heading in rows[0]))


if __name__ == "__main__":
    unittest.main()
