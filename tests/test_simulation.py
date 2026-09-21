import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from jev_demo.historical_data import Bar, MarketSnapshot, Source
from jev_demo.run_store import RunStore
from jev_demo.simulation import SimulationRequest, run_buy_and_hold


class SimulationTests(unittest.TestCase):
    def test_buy_and_hold_completes_and_reconciles_through_the_public_seam(self):
        start = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)
        symbols = ("AAPL", "MSFT", "NVDA")
        bars = tuple(
            Bar(
                symbol,
                (start + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z"),
                100 + minute + offset,
                101 + minute + offset,
                99 + minute + offset,
                100.5 + minute + offset,
                1000,
            )
            for minute in range(63)
            for offset, symbol in enumerate(symbols)
        )
        snapshot = MarketSnapshot("2026-09-18", symbols, bars, Source(), "a" * 64)

        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            run = run_buy_and_hold(SimulationRequest("2026-09-18"), snapshot, store)
            persisted = store.read(run["id"])

        self.assertEqual("completed", run["status"])
        self.assertEqual(run, persisted)
        result = run["result"]
        self.assertEqual(6, len(result["orders"]))
        self.assertEqual(6, len(result["fills"]))
        self.assertEqual(2, len(result["fees"]))
        self.assertEqual(63, len(result["equity_points"]))
        self.assertTrue(all(position["quantity"] == 0 for position in result["positions"]))

        buy_fills = [fill for fill in result["fills"] if fill["side"] == "buy"]
        sell_fills = [fill for fill in result["fills"] if fill["side"] == "sell"]
        self.assertTrue(all(fill["quantity"] == int(fill["quantity"]) for fill in buy_fills))
        self.assertTrue(all(Decimal(fill["notional"]) <= Decimal("10000") for fill in buy_fills))
        self.assertTrue(all(fill["timestamp"] == bars[184].timestamp for fill in buy_fills))
        self.assertTrue(all(
            Decimal(fill["price"]) == Decimal(fill["reference_price"]) * Decimal("1.0002")
            for fill in buy_fills
        ))
        self.assertTrue(all(
            Decimal(fill["price"]) == Decimal(fill["reference_price"]) * Decimal("0.9998")
            for fill in sell_fills
        ))
        self.assertTrue(all(Decimal(point["cash"]) >= 0 for point in result["equity_points"]))

        fees = {fee["kind"]: Decimal(fee["amount"]) for fee in result["fees"]}
        gross_sales = sum(Decimal(fill["notional"]) for fill in sell_fills)
        sold_shares = sum(fill["quantity"] for fill in sell_fills)
        self.assertEqual(
            (gross_sales * Decimal("0.0000206")).quantize(Decimal("0.01"), rounding=ROUND_CEILING),
            fees["sec_section_31"],
        )
        self.assertEqual(
            (Decimal(sold_shares) * Decimal("0.000195")).quantize(Decimal("0.01"), rounding=ROUND_CEILING),
            fees["finra_taf"],
        )

        ledger_cash = sum(Decimal(entry["amount"]) for entry in result["ledger"])
        ending_cash = Decimal(result["ending_cash"])
        self.assertEqual(ending_cash, ledger_cash)
        self.assertEqual(ending_cash, Decimal(result["ending_equity"]))
        self.assertEqual(ending_cash - Decimal("100000"), Decimal(result["net_pnl"]))
        self.assertEqual("0.00", result["reconciliation_difference"])


if __name__ == "__main__":
    unittest.main()
