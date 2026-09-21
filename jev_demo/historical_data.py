"""Validated, immutable Alpaca historical market snapshots."""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


SYMBOLS = ("AAPL", "MSFT", "NVDA")


class HistoricalDataError(ValueError):
    """The requested market snapshot cannot be produced safely."""


@dataclass(frozen=True)
class Source:
    provider: str = "alpaca"
    feed: str = "sip"
    timeframe: str = "1Min"


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class MarketSnapshot:
    trading_date: str
    symbols: tuple[str, ...]
    bars: tuple[Bar, ...]
    source: Source
    digest: str


@dataclass(frozen=True)
class SnapshotResult:
    snapshot: MarketSnapshot
    reused: bool


class AlpacaHistoricalData:
    def __init__(self, key, secret, cache_directory, request=None, now=None, feed="sip"):
        if not key or not secret:
            raise HistoricalDataError("Alpaca credentials are required")
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.cache_directory = Path(cache_directory)
        self.request = request or self._request
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.source = Source(feed=feed)

    def snapshot(self, trading_date, symbols=SYMBOLS):
        try:
            requested_date = trading_date if type(trading_date) is date else date.fromisoformat(trading_date)
            trading_date = requested_date.isoformat()
        except (TypeError, ValueError) as error:
            raise HistoricalDataError("trading date must be YYYY-MM-DD") from error
        if requested_date > self.now().astimezone(ZoneInfo("America/New_York")).date():
            raise HistoricalDataError(f"{trading_date} is in the future")
        symbols = tuple(symbols)
        if (not symbols or len(set(symbols)) != len(symbols)
                or any(not isinstance(symbol, str) or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol)
                       for symbol in symbols)):
            raise HistoricalDataError("symbols must be unique uppercase stock symbols")

        cache_path = self.cache_directory / f"{trading_date}-{'-'.join(symbols)}-{self.source.feed}.json"
        if cache_path.is_file():
            return SnapshotResult(self._read_cache(cache_path, trading_date, symbols), True)

        calendar = self._json(
            "https://api.alpaca.markets/v2/calendar?" + urlencode({"start": trading_date, "end": trading_date})
        )
        if not isinstance(calendar, list):
            raise HistoricalDataError("malformed Alpaca calendar response")
        if not calendar:
            raise HistoricalDataError(f"{trading_date} is not a trading day")
        session = calendar[0]
        try:
            if session["date"] != trading_date:
                raise ValueError
            eastern = ZoneInfo("America/New_York")
            session_open = datetime.fromisoformat(f"{requested_date}T{session['open']}").replace(tzinfo=eastern)
            session_close = datetime.fromisoformat(f"{requested_date}T{session['close']}").replace(tzinfo=eastern)
            if session_open >= session_close:
                raise ValueError
        except (KeyError, TypeError, ValueError) as error:
            raise HistoricalDataError("malformed Alpaca calendar response") from error
        if self.now().astimezone(timezone.utc) < session_close.astimezone(timezone.utc):
            raise HistoricalDataError(f"{trading_date} is not complete")

        bars = self._fetch_bars(symbols, session_open, session_close)
        self._validate_bars(bars)
        self._validate_complete(bars, symbols, session_open, session_close)
        payload = {
            "trading_date": trading_date,
            "symbols": list(symbols),
            "source": asdict(self.source),
            "session_open": session_open.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "session_close": session_close.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "bars": [asdict(bar) for bar in bars],
        }
        digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        payload["digest"] = digest
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return SnapshotResult(self._snapshot(payload), False)

    def _fetch_bars(self, symbols, session_open, session_close):
        parameters = {
            "symbols": ",".join(symbols),
            "timeframe": self.source.timeframe,
            "start": session_open.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "end": session_close.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "feed": self.source.feed,
            "limit": 10000,
            "sort": "asc",
        }
        collected = {symbol: [] for symbol in symbols}
        while True:
            response = self._json("https://data.alpaca.markets/v2/stocks/bars?" + urlencode(parameters))
            try:
                response_bars = response["bars"]
                for symbol in symbols:
                    collected[symbol].extend(response_bars.get(symbol, []))
                token = response.get("next_page_token")
            except (AttributeError, KeyError, TypeError) as error:
                raise HistoricalDataError("malformed Alpaca bars response") from error
            if not token:
                break
            parameters["page_token"] = token

        result = []
        try:
            for symbol, raw_bars in collected.items():
                for raw in raw_bars:
                    timestamp = self._timestamp(raw["t"])
                    prices = raw["o"], raw["h"], raw["l"], raw["c"]
                    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in prices):
                        raise ValueError
                    if isinstance(raw["v"], bool) or not isinstance(raw["v"], int):
                        raise ValueError
                    bar = Bar(symbol, timestamp, float(raw["o"]), float(raw["h"]),
                              float(raw["l"]), float(raw["c"]), int(raw["v"]))
                    if not all(math.isfinite(value) for value in prices) or min(prices) <= 0 or bar.volume < 0:
                        raise ValueError
                    if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close) or bar.low > bar.high:
                        raise ValueError
                    result.append(bar)
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise HistoricalDataError("malformed Alpaca bar") from error
        return tuple(sorted(result, key=lambda bar: (bar.timestamp, bar.symbol)))

    def _validate_complete(self, bars, symbols, session_open, session_close):
        expected_times = []
        minute = session_open.astimezone(timezone.utc)
        while minute < session_close.astimezone(timezone.utc):
            expected_times.append(minute.isoformat().replace("+00:00", "Z"))
            minute += timedelta(minutes=1)
        expected = {(symbol, timestamp) for timestamp in expected_times for symbol in symbols}
        actual = {(bar.symbol, bar.timestamp) for bar in bars}
        if len(actual) != len(bars):
            raise HistoricalDataError("duplicate bars returned by Alpaca")
        if actual != expected:
            missing = len(expected - actual)
            extra = len(actual - expected)
            raise HistoricalDataError(f"incomplete regular-session bars: {missing} missing, {extra} unexpected")

    def _read_cache(self, path, trading_date, symbols):
        try:
            payload = json.loads(path.read_text())
            digest = payload.pop("digest")
            actual = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if digest != actual:
                raise HistoricalDataError("cached snapshot digest mismatch")
            payload["digest"] = digest
            snapshot = self._snapshot(payload)
            if (snapshot.trading_date != trading_date or snapshot.symbols != symbols
                    or snapshot.source != self.source):
                raise HistoricalDataError("cached snapshot metadata mismatch")
            session_open = datetime.fromisoformat(self._timestamp(payload["session_open"]).replace("Z", "+00:00"))
            session_close = datetime.fromisoformat(self._timestamp(payload["session_close"]).replace("Z", "+00:00"))
            self._validate_bars(snapshot.bars)
            self._validate_complete(snapshot.bars, symbols, session_open, session_close)
            return snapshot
        except HistoricalDataError:
            raise
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise HistoricalDataError("malformed cached snapshot") from error

    def _validate_bars(self, bars):
        if tuple(sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))) != bars:
            raise HistoricalDataError("snapshot bars are not ordered")
        try:
            for bar in bars:
                prices = bar.open, bar.high, bar.low, bar.close
                if (self._timestamp(bar.timestamp) != bar.timestamp
                        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in prices)
                        or isinstance(bar.volume, bool) or not isinstance(bar.volume, int)
                        or not all(math.isfinite(value) and value > 0 for value in prices)
                        or bar.volume < 0
                        or bar.low > min(bar.open, bar.close)
                        or bar.high < max(bar.open, bar.close)
                        or bar.low > bar.high):
                    raise ValueError
        except (TypeError, ValueError, OverflowError) as error:
            raise HistoricalDataError("malformed snapshot bar") from error

    def _snapshot(self, payload):
        try:
            return MarketSnapshot(
                payload["trading_date"], tuple(payload["symbols"]),
                tuple(Bar(**bar) for bar in payload["bars"]), Source(**payload["source"]), payload["digest"]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise HistoricalDataError("malformed snapshot") from error

    def _json(self, url):
        try:
            return json.loads(self.request(Request(url, headers=self.headers)))
        except HistoricalDataError:
            raise
        except (HTTPError, URLError, OSError) as error:
            raise HistoricalDataError("Alpaca data unavailable") from error
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
            raise HistoricalDataError("malformed Alpaca response") from error

    @staticmethod
    def _timestamp(value):
        if not isinstance(value, str):
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.second or parsed.microsecond:
            raise ValueError
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _request(request):
        with urlopen(request, timeout=30) as response:
            return response.read()
