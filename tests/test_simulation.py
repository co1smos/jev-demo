import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from jev_demo.historical_data import Bar, MarketSnapshot, Source
from jev_demo.run_store import RunStore
from jev_demo.simulation import SimulationRequest, run_buy_and_hold, run_simulation
from jev_demo.strategy import Action, Trend, crossover_action


class SimulationTests(unittest.TestCase):
    def test_crossover_actions_cover_buy_hold_and_sell(self):
        self.assertEqual(Action.BUY, crossover_action(Trend.BELOW, Trend.ABOVE))
        self.assertEqual(Action.SELL, crossover_action(Trend.ABOVE, Trend.BELOW))
        self.assertEqual(Action.BUY, crossover_action(Trend.EQUAL, Trend.ABOVE))
        self.assertEqual(Action.SELL, crossover_action(Trend.EQUAL, Trend.BELOW))
        self.assertEqual(Action.HOLD, crossover_action(Trend.ABOVE, Trend.ABOVE))
        self.assertEqual(Action.HOLD, crossover_action(None, Trend.ABOVE))

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

    def test_sma_crossover_uses_completed_bars_and_the_same_simulation_seam(self):
        start = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)
        symbols = ("AAPL", "MSFT", "NVDA")
        closes = [100] * 40 + [90] * 20 + [500, 1, 1, 1, 1, 1, 1]
        bars = tuple(
            Bar(
                symbol,
                (start + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z"),
                close,
                close,
                close,
                close,
                1000,
            )
            for minute, close in enumerate(closes)
            for symbol in symbols
        )
        snapshot = MarketSnapshot(
            "2026-09-18",
            symbols,
            bars,
            Source(),
            "b" * 64,
            start.isoformat().replace("+00:00", "Z"),
            (start + timedelta(minutes=len(closes))).isoformat().replace("+00:00", "Z"),
        )

        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            run = run_simulation(
                SimulationRequest("2026-09-18", "sma20_sma60"), snapshot, store
            )

        result = run["result"]
        self.assertEqual("completed", run["status"])
        self.assertEqual("sma20_sma60", result["method"])
        self.assertTrue(all(
            decision["timestamp"] >= bars[180].timestamp
            for decision in result["decisions"]
        ))
        buy_orders = [order for order in result["orders"] if order["side"] == "buy"]
        self.assertEqual(3, len(buy_orders))
        self.assertTrue(all(order["submitted_at"] == bars[183].timestamp for order in buy_orders))
        self.assertTrue(all(order["fill_at"] == bars[186].timestamp for order in buy_orders))
        sell_orders = [
            order for order in result["orders"]
            if order["side"] == "sell" and order["reason"] == "sma20_sma60"
        ]
        self.assertEqual(3, len(sell_orders))
        self.assertTrue(all(order["submitted_at"] == bars[192].timestamp for order in sell_orders))
        self.assertTrue(all(order["fill_at"] == bars[195].timestamp for order in sell_orders))
        self.assertEqual({"BUY", "HOLD", "SELL"}, {
            decision["action"] for decision in result["decisions"]
        })
        self.assertEqual("0.00", result["reconciliation_difference"])
        self.assertTrue(all(position["quantity"] == 0 for position in result["positions"]))

    def test_jev_completes_the_day_with_one_decision_set_per_eligible_minute(self):
        start = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)
        symbols = ("AAPL", "MSFT", "NVDA")
        bars = tuple(
            Bar(
                symbol,
                (start + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z"),
                100,
                101,
                99,
                100,
                1000,
            )
            for minute in range(65)
            for symbol in symbols
        )
        snapshot = MarketSnapshot(
            "2026-09-18",
            symbols,
            bars,
            Source(),
            "c" * 64,
            start.isoformat().replace("+00:00", "Z"),
            (start + timedelta(minutes=65)).isoformat().replace("+00:00", "Z"),
        )
        actions = {
            5: {"AAPL": "BUY", "MSFT": "BUY", "NVDA": "ABSTAIN"},
            4: {"AAPL": "BUY", "MSFT": "SELL", "NVDA": "HOLD"},
            3: {"AAPL": "SELL", "MSFT": "BUY", "NVDA": "BUY"},
            2: {"AAPL": "HOLD", "MSFT": "HOLD", "NVDA": "ABSTAIN"},
        }

        class Provider:
            def __init__(self):
                self.calls = 0

            def decide(self, state, model, question):
                self.calls += 1
                action = actions[state["minutes_remaining"]][state["symbol"]]
                return {
                    "model": model,
                    "action": action,
                    "probabilities": {
                        option: float(option == action) for option in question["options"]
                    },
                }

        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            provider = Provider()
            run = run_simulation(
                SimulationRequest("2026-09-18", "jev"),
                snapshot,
                store,
                decision_provider=provider,
            )
            persisted = store.read(run["id"])
            duplicate = run_simulation(
                SimulationRequest("2026-09-18", "jev"),
                snapshot,
                store,
                run_id=run["id"],
                decision_provider=provider,
            )

        self.assertEqual(run, persisted)
        self.assertEqual(run, duplicate)
        self.assertEqual(12, provider.calls)
        result = run["result"]
        self.assertEqual("completed", run["status"])
        self.assertEqual(12, len(result["decisions"]))
        self.assertEqual(12, len({
            (decision["minute"], decision["symbol"]) for decision in result["decisions"]
        }))
        self.assertEqual(12, len(result["actions"]))
        self.assertEqual(8, len(result["orders"]))
        self.assertEqual(1, len([
            order for order in result["orders"]
            if order["symbol"] == "AAPL" and order["side"] == "buy"
        ]))
        self.assertTrue(all(
            Decimal(fill["notional"]) <= Decimal("10000")
            for fill in result["fills"] if fill["side"] == "buy"
        ))
        self.assertTrue(all(position["quantity"] == 0 for position in result["positions"]))
        self.assertEqual("0.00", result["reconciliation_difference"])
        self.assertEqual(
            12,
            len([record for record in run["records"] if record["kind"].startswith("jev_decision")]),
        )
        self.assertEqual(12, len([record for record in run["records"] if record["kind"] == "action"]))
        self.assertEqual(
            Decimal(result["ending_cash"]),
            sum(
                Decimal(record["data"]["amount"])
                for record in run["records"]
                if record["kind"] == "ledger"
            ),
        )

    def test_concurrent_jev_workers_process_a_run_only_once(self):
        snapshot = self._jev_snapshot()

        class Provider:
            def __init__(self):
                self.calls = 0
                self.lock = threading.Lock()

            def decide(self, state, model, question):
                with self.lock:
                    self.calls += 1
                time.sleep(0.02)
                return {
                    "model": model,
                    "action": "HOLD",
                    "probabilities": {
                        option: float(option == "HOLD") for option in question["options"]
                    },
                }

        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            request = SimulationRequest("2026-09-18", "jev")
            run_id = store.create({**request.__dict__, "source_digest": snapshot.digest})
            provider = Provider()
            barrier = threading.Barrier(2)

            def run():
                barrier.wait()
                return run_simulation(
                    request, snapshot, store, run_id=run_id, decision_provider=provider
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [future.result() for future in (executor.submit(run), executor.submit(run))]
            persisted = store.read(run_id)

        self.assertTrue(any(result["status"] == "completed" for result in results))
        self.assertEqual(12, provider.calls)
        self.assertEqual(12, len([
            record for record in persisted["records"]
            if record["kind"].startswith("jev_decision")
        ]))

    def test_jev_persists_minute_execution_before_a_later_interruption(self):
        snapshot = self._jev_snapshot()

        class Provider:
            def decide(self, state, model, question):
                if state["minutes_remaining"] == 4:
                    raise KeyboardInterrupt
                return {
                    "model": model,
                    "action": "BUY",
                    "probabilities": {
                        option: float(option == "BUY") for option in question["options"]
                    },
                }

        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            request = SimulationRequest("2026-09-18", "jev")
            run_id = store.create({**request.__dict__, "source_digest": snapshot.digest})
            with self.assertRaises(KeyboardInterrupt):
                run_simulation(
                    request, snapshot, store, run_id=run_id, decision_provider=Provider()
                )
            records = store.read(run_id)["records"]

        self.assertEqual(3, len([record for record in records if record["kind"] == "order"]))
        self.assertEqual(3, len([record for record in records if record["kind"] == "fill"]))
        self.assertTrue(any(record["kind"] == "position" for record in records))
        self.assertTrue(any(record["kind"] == "ledger" for record in records))
        self.assertTrue(any(record["kind"] == "equity" for record in records))

    @staticmethod
    def _jev_snapshot():
        start = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)
        symbols = ("AAPL", "MSFT", "NVDA")
        bars = tuple(
            Bar(
                symbol,
                (start + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z"),
                100,
                101,
                99,
                100,
                1000,
            )
            for minute in range(65)
            for symbol in symbols
        )
        return MarketSnapshot(
            "2026-09-18",
            symbols,
            bars,
            Source(),
            "d" * 64,
            start.isoformat().replace("+00:00", "Z"),
            (start + timedelta(minutes=65)).isoformat().replace("+00:00", "Z"),
        )


if __name__ == "__main__":
    unittest.main()
