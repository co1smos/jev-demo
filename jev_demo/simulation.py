"""Deterministic, cash-funded historical simulations."""

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING
from itertools import groupby


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


def run_buy_and_hold(request, snapshot, store):
    """Run and persist the v1 buy-and-hold benchmark."""
    if not isinstance(request, SimulationRequest) or request.method != "buy_and_hold":
        raise ValueError("a buy-and-hold SimulationRequest is required")
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

    run_id = store.create({**asdict(request), "source_digest": snapshot.digest})
    cash = STARTING_CASH
    quantities = {symbol: 0 for symbol in snapshot.symbols}
    costs = {symbol: Decimal("0") for symbol in snapshot.symbols}
    bought_quantities = {}
    orders = []
    fills = []
    position_events = []
    ledger = [{"kind": "deposit", "amount": _text(STARTING_CASH)}]
    equity_points = []

    def order(symbol, side, quantity, submitted, filled, reference, price, reason):
        nonlocal cash
        order_id = f"order-{len(orders) + 1}"
        fill_id = f"fill-{len(fills) + 1}"
        notional = price * quantity
        orders.append({
            "id": order_id, "symbol": symbol, "side": side, "quantity": quantity,
            "submitted_at": submitted, "fill_at": filled, "reason": reason,
        })
        fills.append({
            "id": fill_id, "order_id": order_id, "symbol": symbol, "side": side,
            "quantity": quantity, "timestamp": filled, "reference_price": _text(reference),
            "price": _text(price), "notional": _text(notional),
            "execution_cost": _text(abs(price - reference) * quantity),
        })
        amount = notional if side == "sell" else -notional
        cash += amount
        ledger.append({"kind": f"{side}_fill", "amount": _text(amount), "fill_id": fill_id})

    entry_signal_at, _ = minutes[60]
    entry_at, entry_fills = minutes[61]
    target = STARTING_CASH * POSITION_CAP
    for symbol in snapshot.symbols:
        reference = Decimal(str(entry_fills[symbol].open))
        price = reference * (Decimal("1") + EXECUTION_COST)
        quantity = int(min(target, cash) // price)
        if quantity:
            order(symbol, "buy", quantity, entry_signal_at, entry_at, reference, price, "buy_and_hold")
            quantities[symbol] = quantity
            bought_quantities[symbol] = quantity
            costs[symbol] = price * quantity
            position_events.append({"symbol": symbol, "timestamp": entry_at, "quantity": quantity})
    holding_cash = cash

    exit_signal_at, _ = minutes[-2]
    exit_at, exit_bars = minutes[-1]
    gross_sales = Decimal("0")
    sold_shares = 0
    realized = {}
    for symbol in snapshot.symbols:
        quantity = quantities[symbol]
        reference = Decimal(str(exit_bars[symbol].open))
        price = reference * (Decimal("1") - EXECUTION_COST)
        gross_sales += price * quantity
        sold_shares += quantity
        realized[symbol] = price * quantity - costs[symbol]
        if quantity:
            order(symbol, "sell", quantity, exit_signal_at, exit_at, reference, price, "forced_close")
        quantities[symbol] = 0
        position_events.append({"symbol": symbol, "timestamp": exit_at, "quantity": 0})

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

    for timestamp, bars in minutes:
        marks = Decimal("0")
        # Positions exist from the entry fill until the forced-close fill.
        if entry_at <= timestamp < exit_at:
            marks = sum(Decimal(str(bars[symbol].close)) * bought_quantities.get(symbol, 0)
                        for symbol in snapshot.symbols)
            point_cash = holding_cash
        elif timestamp < entry_at:
            point_cash = STARTING_CASH
        else:
            point_cash = cash
        equity_points.append({"timestamp": timestamp, "cash": _text(point_cash),
                              "equity": _text(point_cash + marks)})

    positions = [
        {"symbol": symbol, "quantity": 0, "realized_pnl": _text(realized[symbol])}
        for symbol in snapshot.symbols
    ]
    ledger_cash = sum(Decimal(entry["amount"]) for entry in ledger)
    result = {
        "method": request.method,
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
    store.append(run_id, [
        *({"kind": "order", "data": item} for item in orders),
        *({"kind": "fill", "data": item} for item in fills),
        *({"kind": "fee", "data": item} for item in fees),
        *({"kind": "position", "data": item} for item in position_events),
        *({"kind": "equity", "data": item} for item in equity_points),
        *({"kind": "ledger", "data": item} for item in ledger),
    ])
    store.complete(run_id, result)
    return store.read(run_id)
