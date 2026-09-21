import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import tempfile
import unittest
from pathlib import Path

from jev_demo.decision import TypeSafeDecisionProvider, obtain_decision, obtain_minute_decisions
from jev_demo.run_store import RunStore
from jev_demo.strategy import AccountSnapshot, DecisionRequest, Position, PositionState, StrategyFeatures, Trend
from test_strategy import market


REQUEST = DecisionRequest(
    "trend_momentum_v1",
    "AAPL",
    "2026-09-18T14:30:00Z",
    StrategyFeatures(149.5, 129.5, Trend.ABOVE, 0.23, 0.001, 1.07, PositionState.FLAT, 0, 330),
)


class FakeProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def decide(self, state, model, question):
        self.calls.append((state, model, question))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = RunStore(Path(self.temporary.name) / "runs.sqlite3")
        self.run_id = self.store.create({"trading_date": "2026-09-18"})

    def tearDown(self):
        self.temporary.cleanup()

    def test_minute_waits_for_slow_stock_and_isolates_its_failure(self):
        for failure in (TimeoutError(), {"action": "INVALID"}):
            with self.subTest(failure=failure):
                release = Event()
                finished = {symbol: Event() for symbol in ("MSFT", "NVDA")}
                calls = {symbol: [] for symbol in ("AAPL", "MSFT", "NVDA")}
                account = AccountSnapshot((Position("MSFT", 7), Position("NVDA", 9)))
                original = AccountSnapshot(account.positions)

                class Provider:
                    def decide(self, state, model, question):
                        symbol = state["symbol"]
                        calls[symbol].append(state)
                        if symbol == "AAPL":
                            if not release.wait(5):
                                raise TimeoutError()
                            if isinstance(failure, Exception):
                                raise failure
                            return failure
                        if symbol == "MSFT":
                            finished["NVDA"].wait(5)
                        action = {"MSFT": "SELL", "NVDA": "BUY"}[symbol]
                        finished[symbol].set()
                        return {"model": model, "action": action, "probabilities": {
                            option: float(option == action)
                            for option in ("BUY", "HOLD", "SELL", "ABSTAIN")
                        }}

                with ThreadPoolExecutor(max_workers=1) as executor:
                    pending = executor.submit(
                        obtain_minute_decisions, self.run_id, market(), account,
                        REQUEST.minute, Provider(), self.store,
                    )
                    try:
                        for done in finished.values():
                            self.assertTrue(done.wait(2), "other stocks must run while AAPL waits")
                        self.assertFalse(pending.done(), "a partial decision set must not escape")
                        self.assertEqual(original, account)
                    finally:
                        release.set()
                    decisions = pending.result(timeout=5)

                self.assertEqual({"AAPL": "ABSTAIN", "MSFT": "SELL", "NVDA": "BUY"},
                                 {symbol: value["action"] for symbol, value in decisions.items()})
                for symbol, quantity in (("AAPL", 0), ("MSFT", 7), ("NVDA", 9)):
                    self.assertEqual(symbol, decisions[symbol]["symbol"])
                    self.assertEqual(REQUEST.minute, decisions[symbol]["minute"])
                    self.assertEqual(quantity, calls[symbol][0]["position_quantity"])
                    self.assertEqual(3 if symbol == "AAPL" else 1, len(calls[symbol]))
                self.assertEqual(original, account)
                records = self.store.read(self.run_id)["records"][-3:]
                self.assertEqual(set(decisions), {record["data"]["symbol"] for record in records})
                self.assertTrue(all(record["kind"].startswith("jev_decision") for record in records))

    def test_ineligible_minute_does_not_start_calls_or_persist_partial_results(self):
        provider = FakeProvider([])
        with self.assertRaises(ValueError):
            obtain_minute_decisions(
                self.run_id, market(), AccountSnapshot(),
                "2026-09-18T14:29:00Z", provider, self.store,
            )
        self.assertEqual([], provider.calls)
        self.assertEqual([], self.store.read(self.run_id)["records"])

    def test_fake_provider_returns_and_persists_a_bounded_decision(self):
        provider = FakeProvider([{
            "model": "jev-1.13.0",
            "action": "BUY",
            "probabilities": {"BUY": 0.7, "HOLD": 0.2, "SELL": 0.05, "ABSTAIN": 0.05},
        }])

        decision = obtain_decision(self.run_id, REQUEST, provider, self.store)

        self.assertEqual("BUY", decision["action"])
        state, model, question = provider.calls[0]
        self.assertEqual("jev-1.13.0", model)
        self.assertEqual(["ABSTAIN", "BUY", "HOLD", "SELL"], sorted(question["options"]))
        self.assertEqual(
            {"symbol", "sma20", "sma60", "trend", "momentum_30", "volatility_20", "relative_volume",
             "position_state", "position_quantity", "minutes_remaining"},
            set(state),
        )
        record = self.store.read(self.run_id)["records"][-1]
        self.assertEqual("jev_decision", record["kind"])
        self.assertEqual("trend_momentum_v1", record["data"]["input_version"])
        self.assertEqual("stock_action_v1", record["data"]["question_version"])
        self.assertEqual("jev-1.13.0", record["data"]["requested_model"])
        self.assertEqual("jev-1.13.0", record["data"]["returned_model"])

    def test_provider_failures_and_invalid_responses_abstain_after_bounded_retries(self):
        failures = [
            TimeoutError(),
            {
                "model": "jev-latest",
                "action": "BUY",
                "probabilities": {"BUY": 0.7, "HOLD": 0.1, "SELL": 0.1, "ABSTAIN": 0.1},
            },
            {"model": "jev-1.13.0", "action": "BUY", "probabilities": {"BUY": 1.0}},
            {
                "model": "jev-1.13.0",
                "action": "WAIT",
                "probabilities": {"BUY": 0.25, "HOLD": 0.25, "SELL": 0.25, "ABSTAIN": 0.25},
            },
        ]

        for response in failures:
            with self.subTest(response=response):
                provider = FakeProvider([response, response, response])
                decision = obtain_decision(self.run_id, REQUEST, provider, self.store)
                self.assertEqual("ABSTAIN", decision["action"])
                self.assertEqual(3, len(provider.calls))

        error_records = [record for record in self.store.read(self.run_id)["records"]
                         if record["kind"] == "jev_decision_error"]
        self.assertEqual(4, len(error_records))
        self.assertTrue(all(record["data"]["error"] for record in error_records))

    def test_a_retry_can_recover_without_persisting_the_transient_error(self):
        valid = {
            "model": "jev-1.13.0",
            "action": "HOLD",
            "probabilities": {"BUY": 0.1, "HOLD": 0.7, "SELL": 0.1, "ABSTAIN": 0.1},
        }
        provider = FakeProvider([TimeoutError(), valid])

        decision = obtain_decision(self.run_id, REQUEST, provider, self.store)

        self.assertEqual("HOLD", decision["action"])
        self.assertEqual(2, len(provider.calls))
        self.assertEqual(["jev_decision"], [record["kind"] for record in self.store.read(self.run_id)["records"]])

    def test_typesafe_provider_sends_the_key_only_as_authorization(self):
        captured = []

        def request(http_request):
            captured.append(http_request)
            return json.dumps({
                "model": "jev-1.13.0",
                "answers": {"action": {
                    "type": "choice",
                    "choice": "SELL",
                    "probabilities": {"BUY": 0.1, "HOLD": 0.1, "SELL": 0.7, "ABSTAIN": 0.1},
                    "confidence": 0.8,
                }},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }).encode()

        decision = obtain_decision(
            self.run_id, REQUEST, TypeSafeDecisionProvider("typesafe-secret", request=request), self.store
        )

        body = json.loads(captured[0].data)
        self.assertEqual("SELL", decision["action"])
        self.assertEqual("Bearer typesafe-secret", captured[0].get_header("Authorization"))
        self.assertNotIn("typesafe-secret", json.dumps(body))
        self.assertEqual("jev-1.13.0", body["model"])
        self.assertEqual({"symbol", *REQUEST.features.__dataclass_fields__}, set(body["state"]))


if __name__ == "__main__":
    unittest.main()
