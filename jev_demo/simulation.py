"""Deterministic, cash-funded historical simulations."""

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING
from itertools import groupby

from .strategy import AccountSnapshot, Action, Position, TrendMomentumV1, crossover_action

STARTING_CASH = Decimal("100000")
POSITION_CAP = Decimal("0.10")
EXECUTION_COST = Decimal("0.0002")
SEC_RATE = Decimal("0.0000206")
TAF_RATE = Decimal("0.000195")
TAF_CAP = Decimal("9.79")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class SimulationRequest:
    trading_date: str
    method: str = "buy_and_hold"


def _text(value):
    return format(value, "f")


def _fee(value):
    return value.quantize(CENT, rounding=ROUND_CEILING)


def run_simulation(request, snapshot, store, run_id=None):
    """Run a supported method through the shared persisted simulation seam."""
    if not isinstance(request, SimulationRequest):
        raise ValueError("a SimulationRequest is required")
    if request.method == "buy_and_hold":
        return run_buy_and_hold(request, snapshot, store, run_id)
    if request.method == "sma20_sma60":
        if run_id is not None:
            raise ValueError("an existing run is only supported for buy_and_hold")
        return run_sma_crossover(request, snapshot, store)
    raise ValueError(f"unsupported simulation method: {request.method}")


def run_buy_and_hold(request, snapshot, store, run_id=None):
    """Run and persist the v1 buy-and-hold benchmark."""
    if not isinstance(request, SimulationRequest) or request.method != "buy_and_hold":
        raise ValueError("a buy-and-hold SimulationRequest is required")

    def decisions(index, _quantities):
        return {symbol: Action.BUY for symbol in snapshot.symbols} if index == 60 else {}

    return _run(request, snapshot, store, decisions, run_id=run_id)


def run_sma_crossover(request, snapshot, store):
    """Run and persist the deterministic SMA20/SMA60 comparison."""
    if not isinstance(request, SimulationRequest) or request.method != "sma20_sma60":
        raise ValueError("an sma20_sma60 SimulationRequest is required")

    strategy = TrendMomentumV1()
    previous = {symbol: None for symbol in snapshot.symbols}
    recorded = []

    def decisions(index, quantities):
        minute = snapshot.bars[index * len(snapshot.symbols)].timestamp
        account = AccountSnapshot(tuple(
            Position(symbol, quantity) for symbol, quantity in quantities.items() if quantity
        ))
        actions = {}
        for symbol in snapshot.symbols:
            decision = strategy.request(snapshot, account, symbol, minute)
            if decision is None:
                continue
            action = crossover_action(previous[symbol], decision.features.trend)
            previous[symbol] = decision.features.trend
            recorded.append({
                "symbol": symbol,
                "timestamp": minute,
                "action": action.value,
                "sma20": decision.features.sma20,
                "sma60": decision.features.sma60,
            })
            actions[symbol] = action
        return actions

    return _run(request, snapshot, store, decisions, recorded)


def _run(request, snapshot, store, decide, decisions=None, run_id=None):
    if request.trading_date != snapshot.trading_date:
        raise ValueError("request and snapshot trading dates differ")

    minutes = []
    for timestamp, bars in groupby(snapshot.bars, key=lambda bar: bar.timestamp):
        bars = tuple(bars)
        by_symbol = {bar.symbol: bar for bar in bars}
        if len(bars) != len(snapshot.symbols) or tuple(sorted(by_symbol)) != tuple(sorted(snapshot.symbols)):
            raise ValueError("snapshot must contain one bar per symbol and minute")
        minutes.append((timestamp, by_symbol))
    if len(minutes) < 62:
        raise ValueError("snapshot needs 60 warm-up minutes and later fill minutes")

    run_id = run_id or store.create({**asdict(request), "source_digest": snapshot.digest})
    cash = STARTING_CASH
    quantities = {symbol: 0 for symbol in snapshot.symbols}
    costs = {symbol: Decimal("0") for symbol in snapshot.symbols}
    realized = {symbol: Decimal("0") for symbol in snapshot.symbols}
    orders = []
    fills = []
    position_events = []
    ledger = [{"kind": "deposit", "amount": _text(STARTING_CASH)}]
    equity_points = []
    pending = {}
    gross_sales = Decimal("0")
    sold_shares = 0

    def fill(symbol, side, quantity, submitted, timestamp, reference, reason):
        nonlocal cash, gross_sales, sold_shares
        price = reference * (Decimal("1") + EXECUTION_COST if side == "buy" else Decimal("1") - EXECUTION_COST)
        notional = price * quantity
        order_id = f"order-{len(orders) + 1}"
        fill_id = f"fill-{len(fills) + 1}"
        orders.append({
            "id": order_id, "symbol": symbol, "side": side, "quantity": quantity,
            "submitted_at": submitted, "fill_at": timestamp, "reason": reason,
        })
        fills.append({
            "id": fill_id, "order_id": order_id, "symbol": symbol, "side": side,
            "quantity": quantity, "timestamp": timestamp, "reference_price": _text(reference),
            "price": _text(price), "notional": _text(notional),
            "execution_cost": _text(abs(price - reference) * quantity),
        })
        amount = notional if side == "sell" else -notional
        cash += amount
        ledger.append({"kind": f"{side}_fill", "amount": _text(amount), "fill_id": fill_id})
        if side == "buy":
            quantities[symbol] = quantity
            costs[symbol] = notional
        else:
            quantities[symbol] = 0
            realized[symbol] += notional - costs[symbol]
            costs[symbol] = Decimal("0")
            gross_sales += notional
            sold_shares += quantity
        position_events.append({"symbol": symbol, "timestamp": timestamp, "quantity": quantities[symbol]})

    for index, (timestamp, bars) in enumerate(minutes):
        submitted, actions = pending.pop(index, (None, {}))
        signal_equity = cash + sum(
            Decimal(str(bars[item].open)) * quantity for item, quantity in quantities.items()
        )
        for symbol in snapshot.symbols:
            action = actions.get(symbol, Action.HOLD)
            reference = Decimal(str(bars[symbol].open))
            if (action is Action.BUY and not quantities[symbol]
                    and (request.method == "buy_and_hold" or index < len(minutes) - 1)):
                price = reference * (Decimal("1") + EXECUTION_COST)
                quantity = int(min(signal_equity * POSITION_CAP, cash) // price)
                if quantity:
                    fill(symbol, "buy", quantity, submitted, timestamp, reference, request.method)
            elif action is Action.SELL and quantities[symbol]:
                fill(symbol, "sell", quantities[symbol], submitted, timestamp, reference, request.method)

        if index == len(minutes) - 1:
            signal_at = minutes[index - 1][0]
            for symbol in snapshot.symbols:
                if quantities[symbol]:
                    fill(symbol, "sell", quantities[symbol], signal_at, timestamp,
                         Decimal(str(bars[symbol].open)), "forced_close")

        marks = sum(Decimal(str(bars[symbol].close)) * quantities[symbol] for symbol in snapshot.symbols)
        equity_points.append({"timestamp": timestamp, "cash": _text(cash), "equity": _text(cash + marks)})
        if 60 <= index < len(minutes) - 1:
            pending[index + 1] = (timestamp, decide(index, quantities))

    sec_fee = _fee(gross_sales * SEC_RATE) if request.trading_date >= "2026-04-04" else Decimal("0")
    taf_fee = _fee(min(Decimal(sold_shares) * TAF_RATE, TAF_CAP))
    fees = [
        {"kind": "sec_section_31", "amount": _text(sec_fee)},
        {"kind": "finra_taf", "amount": _text(taf_fee)},
    ]
    for fee in fees:
        amount = Decimal(fee["amount"])
        cash -= amount
        ledger.append({"kind": fee["kind"], "amount": _text(-amount)})
    equity_points[-1]["cash"] = equity_points[-1]["equity"] = _text(cash)

    positions = [
        {"symbol": symbol, "quantity": 0, "realized_pnl": _text(realized[symbol])}
        for symbol in snapshot.symbols
    ]
    ledger_cash = sum(Decimal(entry["amount"]) for entry in ledger)
    result = {
        "method": request.method,
        "source_digest": snapshot.digest,
        "starting_cash": _text(STARTING_CASH),
        "ending_cash": _text(cash),
        "ending_equity": _text(cash),
        "net_pnl": _text(cash - STARTING_CASH),
        "orders": orders,
        "fills": fills,
        "fees": fees,
        "positions": positions,
        "equity_points": equity_points,
        "ledger": ledger,
        "reconciliation_difference": _text((cash - ledger_cash).quantize(CENT)),
        "execution_model_version": "next_minute_open_2bps_v1",
        "fee_version": "us_equity_2026_v1",
    }
    if decisions is not None:
        result["decisions"] = decisions
    store.append(run_id, [
        *({"kind": "decision", "data": item} for item in decisions or ()),
        *({"kind": "order", "data": item} for item in orders),
        *({"kind": "fill", "data": item} for item in fills),
        *({"kind": "fee", "data": item} for item in fees),
        *({"kind": "position", "data": item} for item in position_events),
        *({"kind": "equity", "data": item} for item in equity_points),
        *({"kind": "ledger", "data": item} for item in ledger),
    ])
    store.progress(run_id, 2, 2)
    store.complete(run_id, result)
    return store.read(run_id)
