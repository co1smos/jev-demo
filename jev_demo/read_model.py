"""Dashboard metrics derived only from immutable completed runs."""

from decimal import Decimal


METHODS = ("jev", "sma20_sma60", "buy_and_hold")
ASSUMPTIONS = (
    "source_digest",
    "starting_cash",
    "allocation_cap",
    "execution_model_version",
    "fee_version",
)


def _text(value):
    return format(value, "f")


def _metrics(result):
    starting = Decimal(result["starting_cash"])
    ending = Decimal(result["ending_equity"])
    peak = starting
    maximum_drawdown = Decimal("0")
    maximum_drawdown_return = Decimal("0")
    for point in result["equity_points"]:
        equity = Decimal(point["equity"])
        peak = max(peak, equity)
        drawdown = peak - equity
        if drawdown > maximum_drawdown:
            maximum_drawdown = drawdown
        maximum_drawdown_return = max(maximum_drawdown_return, drawdown / peak)
    contributions = {}
    for fill in result["fills"]:
        amount = Decimal(fill["notional"])
        if fill["side"] == "buy":
            amount = -amount
        contributions[fill["symbol"]] = contributions.get(fill["symbol"], Decimal("0")) + amount
    return {
        "method": result["method"],
        "net_profit": _text(ending - starting),
        "return": _text((ending - starting) / starting),
        "maximum_drawdown": _text(maximum_drawdown),
        "maximum_drawdown_return": _text(maximum_drawdown_return),
        "trade_count": len(result["fills"]),
        "total_costs": _text(sum(
            (Decimal(fill["execution_cost"]) for fill in result["fills"]),
            sum((Decimal(fee["amount"]) for fee in result["fees"]), Decimal("0")),
        )),
        "per_stock_contribution": {
            symbol: _text(value) for symbol, value in contributions.items()
        },
        "equity_curve": [
            {"timestamp": point["timestamp"], "equity": point["equity"]}
            for point in result["equity_points"]
        ],
    }


def comparison(store, run_id):
    """Return the three-method dashboard contract for a completed run."""
    selected = store.read(run_id)
    if selected["status"] != "completed":
        raise ValueError("comparison requires a completed run")
    assumptions = {key: selected["result"][key] for key in ASSUMPTIONS}
    comparison_group_id = selected["result"]["comparison_group_id"]
    trading_date = selected["request"]["trading_date"]
    runs = {selected["result"]["method"]: selected["result"]}
    for run in store.list():
        result = run["result"]
        if (run["status"] == "completed"
                and run["request"].get("trading_date") == trading_date
                and result.get("method") in METHODS
                and result.get("comparison_group_id") == comparison_group_id
                and all(result.get(key) == value for key, value in assumptions.items())):
            runs.setdefault(result["method"], result)
    missing = set(METHODS) - runs.keys()
    if missing:
        raise ValueError(f"missing comparable methods: {', '.join(sorted(missing))}")
    methods = [_metrics(runs[method]) for method in METHODS]
    benchmark = methods[-1]
    for method in methods:
        method["difference_from_buy_and_hold"] = {
            "net_profit": _text(Decimal(method["net_profit"]) - Decimal(benchmark["net_profit"])),
            "return": _text(Decimal(method["return"]) - Decimal(benchmark["return"])),
        }
    return {"run_id": run_id, "shared_assumptions": assumptions, "methods": methods}


def visualization(store, run_id, cache_directory):
    """Join immutable local bars to stored decisions; never request market data."""
    from bisect import bisect_left
    from dataclasses import asdict
    from pathlib import Path
    from .audit import read_audit
    from .historical_data import AlpacaHistoricalData, HistoricalDataError

    run = store.read(run_id)
    if run['status'] != 'completed' or run['result'].get('method') != 'jev':
        raise ValueError('visualization requires a completed JEV run')
    trading_date = run['request']['trading_date']
    symbols = tuple(run['request'].get('symbols', ()))
    digest = run['result']['source_digest']
    snapshot = None
    # Scan local cache names only: the run predates persisted feed metadata.
    for path in sorted(Path(cache_directory).glob('*.json')):
        try:
            candidate = AlpacaHistoricalData.read_cache(path, trading_date, symbols)
        except (HistoricalDataError, UnicodeError):
            continue
        if candidate.digest == digest:
            snapshot = candidate
            break
    if snapshot is None:
        raise ValueError('Exact historical snapshot unavailable or invalid; visualization cannot load')
    bars = {symbol: [asdict(bar) for bar in snapshot.bars if bar.symbol == symbol]
            for symbol in symbols}
    times = {symbol: [bar['timestamp'] for bar in series] for symbol, series in bars.items()}
    decisions = read_audit(store, run_id)['decisions']
    for decision in decisions:
        index = bisect_left(times[decision['symbol']], decision['minute']) - 1
        decision['reference_bar'] = bars[decision['symbol']][index] if index >= 0 else None
    reasons = {order['id']: order['reason'] for order in run['result']['orders']}
    return dict(run_id=run_id, trading_date=trading_date, source_digest=digest,
                symbols=bars, decisions=decisions,
                fills=[{**fill, 'reason': reasons[fill['order_id']]} for fill in run['result']['fills']])
