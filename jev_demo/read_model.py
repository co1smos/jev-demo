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
            maximum_drawdown_return = drawdown / peak
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
    trading_date = selected["request"]["trading_date"]
    runs = {}
    for run in store.list():
        result = run["result"]
        if (run["status"] == "completed"
                and run["request"].get("trading_date") == trading_date
                and result.get("method") in METHODS
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
