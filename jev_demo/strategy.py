"""Replaceable strategy input seam."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from statistics import fmean, pstdev
from typing import Protocol

from .historical_data import MarketSnapshot


class Trend(Enum):
    ABOVE = "above"
    BELOW = "below"
    EQUAL = "equal"


class PositionState(Enum):
    FLAT = "flat"
    LONG = "long"


class Action(Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int


@dataclass(frozen=True)
class AccountSnapshot:
    positions: tuple[Position, ...] = ()


@dataclass(frozen=True)
class StrategyFeatures:
    sma20: float
    sma60: float
    trend: Trend
    momentum_30: float
    volatility_20: float
    relative_volume: float
    position_state: PositionState
    position_quantity: int
    minutes_remaining: int


@dataclass(frozen=True)
class DecisionRequest:
    strategy_version: str
    symbol: str
    minute: str
    features: StrategyFeatures


class Strategy(Protocol):
    def request(
        self, market: MarketSnapshot, account: AccountSnapshot, symbol: str, minute: str
    ) -> DecisionRequest | None: ...


def strategy_request(strategy: Strategy, market: MarketSnapshot, account: AccountSnapshot, symbol: str, minute: str):
    return strategy.request(market, account, symbol, minute)


def crossover_action(previous_trend, trend):
    if previous_trend in (Trend.BELOW, Trend.EQUAL) and trend is Trend.ABOVE:
        return Action.BUY
    if previous_trend in (Trend.ABOVE, Trend.EQUAL) and trend is Trend.BELOW:
        return Action.SELL
    return Action.HOLD


class TrendMomentumV1:
    version = "trend_momentum_v1"

    def request(self, market, account, symbol, minute):
        decision_time = _utc_minute(minute)
        session_open = _utc_minute(market.session_open)
        session_close = _utc_minute(market.session_close)
        if symbol not in market.symbols or not session_open < decision_time < session_close:
            return None

        bars = [bar for bar in market.bars if bar.symbol == symbol and _utc_minute(bar.timestamp) < decision_time]
        window = bars[-60:]
        expected = [decision_time - timedelta(minutes=offset) for offset in range(60, 0, -1)]
        if len(window) != 60 or [_utc_minute(bar.timestamp) for bar in window] != expected:
            return None

        closes = [bar.close for bar in window]
        sma20, sma60 = fmean(closes[-20:]), fmean(closes)
        position = next((position for position in account.positions if position.symbol == symbol), None)
        quantity = position.quantity if position else 0
        returns = [new / old - 1 for old, new in zip(closes[-21:-1], closes[-20:])]
        average_volume = fmean(bar.volume for bar in window[-21:-1])
        features = StrategyFeatures(
            sma20,
            sma60,
            Trend.ABOVE if sma20 > sma60 else Trend.BELOW if sma20 < sma60 else Trend.EQUAL,
            closes[-1] / closes[-31] - 1,
            pstdev(returns),
            window[-1].volume / average_volume if average_volume else 0.0,
            PositionState.LONG if quantity else PositionState.FLAT,
            quantity,
            int((session_close - decision_time).total_seconds() // 60),
        )
        return DecisionRequest(self.version, symbol, minute, features)


def _utc_minute(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("minute must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.second or parsed.microsecond:
        raise ValueError("minute must be a timezone-aware whole minute")
    return parsed.astimezone(timezone.utc)
