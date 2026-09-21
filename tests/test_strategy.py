import unittest
from dataclasses import replace

from jev_demo.historical_data import Bar, MarketSnapshot, Source
from jev_demo.strategy import (
    AccountSnapshot,
    Position,
    PositionState,
    Trend,
    TrendMomentumV1,
    strategy_request,
)


def market(minutes=390):
    bars = tuple(
        Bar(
            symbol,
            f"2026-09-18T{13 + (30 + minute) // 60:02d}:{(30 + minute) % 60:02d}:00Z",
            100 + minute,
            101 + minute,
            99 + minute,
            100 + minute,
            1000 + 10 * minute,
        )
        for minute in range(minutes)
        for symbol in ("AAPL", "MSFT", "NVDA")
    )
    return MarketSnapshot(
        "2026-09-18",
        ("AAPL", "MSFT", "NVDA"),
        bars,
        Source(),
        "digest",
        "2026-09-18T13:30:00Z",
        "2026-09-18T20:00:00Z",
    )


class StrategyTests(unittest.TestCase):
    def test_builds_versioned_request_from_only_completed_bars(self):
        request = strategy_request(
            TrendMomentumV1(),
            market(),
            AccountSnapshot((Position("AAPL", 4),)),
            "AAPL",
            "2026-09-18T14:30:00Z",
        )

        self.assertEqual("trend_momentum_v1", request.strategy_version)
        self.assertEqual("AAPL", request.symbol)
        self.assertEqual("2026-09-18T14:30:00Z", request.minute)
        self.assertEqual(Trend.ABOVE, request.features.trend)
        self.assertAlmostEqual(149.5, request.features.sma20)
        self.assertAlmostEqual(129.5, request.features.sma60)
        self.assertAlmostEqual(159 / 129 - 1, request.features.momentum_30)
        self.assertGreater(request.features.volatility_20, 0)
        self.assertAlmostEqual(1590 / 1485, request.features.relative_volume)
        self.assertEqual(PositionState.LONG, request.features.position_state)
        self.assertEqual(4, request.features.position_quantity)
        self.assertEqual(330, request.features.minutes_remaining)

    def test_returns_none_during_warmup_or_when_the_completed_window_is_missing(self):
        strategy = TrendMomentumV1()
        account = AccountSnapshot()

        self.assertIsNone(strategy_request(strategy, market(60), account, "AAPL", "2026-09-18T14:29:00Z"))
        missing = market()
        missing = replace(missing, bars=tuple(bar for bar in missing.bars if not (
            bar.symbol == "AAPL" and bar.timestamp == "2026-09-18T14:29:00Z"
        )))
        self.assertIsNone(strategy_request(strategy, missing, account, "AAPL", "2026-09-18T14:30:00Z"))

        zero_volume = market()
        zero_volume = replace(zero_volume, bars=tuple(
            replace(bar, volume=0) if bar.symbol == "AAPL" else bar for bar in zero_volume.bars
        ))
        self.assertEqual(
            0.0,
            strategy_request(strategy, zero_volume, account, "AAPL", "2026-09-18T14:30:00Z").features.relative_volume,
        )

    def test_strategy_is_replaceable_without_changing_the_caller(self):
        class OtherStrategy:
            def request(self, market, account, symbol, minute):
                return replace(
                    TrendMomentumV1().request(market, account, symbol, minute),
                    strategy_version="other_v1",
                )

        result = strategy_request(OtherStrategy(), market(), AccountSnapshot(), "MSFT", "2026-09-18T14:30:00Z")

        self.assertEqual("other_v1", result.strategy_version)
        self.assertEqual("MSFT", result.symbol)


if __name__ == "__main__":
    unittest.main()
