import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jev_demo.historical_data import AlpacaHistoricalData, HistoricalDataError


class HistoricalDataTests(unittest.TestCase):
    def test_rejects_cached_snapshot_until_session_is_complete(self):
        calendar = [{"date": "2026-09-18", "open": "09:30", "close": "09:31"}]
        bars = {
            symbol: [{"t": "2026-09-18T13:30:00Z", "o": 100, "h": 101,
                      "l": 99, "c": 100.5, "v": 1000}]
            for symbol in ("AAPL", "MSFT", "NVDA")
        }
        responses = iter((calendar, {"bars": bars}))
        current_time = [datetime(2026, 9, 18, 13, 32, tzinfo=timezone.utc)]

        with tempfile.TemporaryDirectory() as directory:
            service = AlpacaHistoricalData(
                "key", "secret", directory,
                request=lambda _request: json.dumps(next(responses)).encode(),
                now=lambda: current_time[0],
            )
            service.snapshot("2026-09-18")
            current_time[0] = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)

            with self.assertRaisesRegex(HistoricalDataError, "not complete"):
                service.snapshot("2026-09-18")

    def test_returns_validated_snapshot_then_reuses_it_without_another_request(self):
        calls = []
        available_bars = {
            symbol: [
                {"t": timestamp, "o": 100 + minute, "h": 101 + minute,
                 "l": 99 + minute, "c": 100.5 + minute, "v": 1000}
                for minute, timestamp in enumerate((
                    "2026-09-18T13:30:00Z",
                    "2026-09-18T13:31:00Z",
                    "2026-09-18T13:32:00Z",
                ))
            ]
            for symbol in ("AAPL", "MSFT", "NVDA")
        }

        def request(http_request):
            calls.append(http_request.full_url)
            if "/v2/calendar" in http_request.full_url:
                payload = [{"date": "2026-09-18", "open": "09:30", "close": "09:32"}]
            else:
                end = parse_qs(urlparse(http_request.full_url).query)["end"][0]
                payload = {
                    "bars": {
                        symbol: [bar for bar in bars if bar["t"] <= end]
                        for symbol, bars in available_bars.items()
                    },
                    "next_page_token": None,
                }
            return json.dumps(payload).encode()

        with tempfile.TemporaryDirectory() as directory:
            service = AlpacaHistoricalData(
                "key", "secret", Path(directory), request=request,
                now=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc),
            )
            first = service.snapshot(date(2026, 9, 18))
            second = service.snapshot("2026-09-18")

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.snapshot, second.snapshot)
        self.assertEqual(("AAPL", "MSFT", "NVDA"), first.snapshot.symbols)
        self.assertEqual(6, len(first.snapshot.bars))
        self.assertEqual(sorted(first.snapshot.bars, key=lambda bar: (bar.timestamp, bar.symbol)), list(first.snapshot.bars))
        self.assertEqual("alpaca", first.snapshot.source.provider)
        self.assertEqual("sip", first.snapshot.source.feed)
        self.assertEqual(64, len(first.snapshot.digest))
        self.assertEqual(2, len(calls))

    def test_rejects_invalid_or_unavailable_days_explicitly(self):
        complete = datetime(2026, 9, 19, tzinfo=timezone.utc)

        def service(responses, now=complete):
            responses = iter(responses)

            def request(_request):
                response = next(responses)
                if isinstance(response, Exception):
                    raise response
                return json.dumps(response).encode()

            directory = tempfile.TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            return AlpacaHistoricalData("key", "secret", directory.name, request=request, now=lambda: now)

        calendar = [{"date": "2026-09-18", "open": "09:30", "close": "09:32"}]
        valid_bar = {"t": "2026-09-18T13:30:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 1000}
        cases = {
            "holiday": (service([[]]), "not a trading day"),
            "future": (service([], now=datetime(2026, 9, 17, tzinfo=timezone.utc)), "future"),
            "incomplete": (service([calendar], now=datetime(2026, 9, 18, 13, 31, tzinfo=timezone.utc)), "not complete"),
            "gap": (service([calendar, {"bars": {symbol: [valid_bar] for symbol in ("AAPL", "MSFT", "NVDA")}}]), "missing"),
            "malformed": (service([calendar, {"bars": {"AAPL": [{"bad": "bar"}]}}]), "malformed"),
            "malformed timestamp": (service([calendar, {"bars": {"AAPL": [{**valid_bar, "t": None}]}}]), "malformed"),
            "unavailable": (service([OSError("offline")]), "unavailable"),
        }
        for name, (data, message) in cases.items():
            with self.subTest(name=name), self.assertRaisesRegex(HistoricalDataError, message):
                data.snapshot("2026-09-18")


if __name__ == "__main__":
    unittest.main()
