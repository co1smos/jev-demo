"""Stored JEV decision audit read model and CSV export."""

import csv
import io


CSV_COLUMNS = (
    "minute", "symbol", "action",
    "buy_probability", "hold_probability", "sell_probability", "abstain_probability",
    "sma20", "sma60", "trend", "momentum_30", "volatility_20", "relative_volume",
    "position_state", "position_quantity", "minutes_remaining",
    "input_version", "question_version", "requested_model", "returned_model",
    "explanation", "error", "order_ids", "fill_ids",
)


def read_audit(store, run_id, symbol=None, action=None, minute=None):
    """Return filtered audit evidence derived only from one completed stored run."""
    run = store.read(run_id)
    if run["status"] != "completed":
        raise ValueError("audit is available only for completed runs")
    result = run["result"] or {}
    actions = {
        (item["symbol"], item["minute"]): item
        for item in result.get("actions", ())
    }
    orders = result.get("orders", ())
    fills = result.get("fills", ())
    decisions = []
    for decision in result.get("decisions", ()):
        if ((symbol and decision.get("symbol") != symbol)
                or (action and decision.get("action") != action)
                or (minute and decision.get("minute") != minute)):
            continue
        linked_orders = [item for item in orders
                         if item.get("symbol") == decision.get("symbol")
                         and item.get("submitted_at") == decision.get("minute")
                         and item.get("reason") == "jev"]
        order_ids = {item.get("id") for item in linked_orders}
        linked_fills = [item for item in fills if item.get("order_id") in order_ids]
        action_record = actions.get((decision.get("symbol"), decision.get("minute")), {})
        decisions.append({
            **decision,
            "explanation": action_record.get("explanation"),
            "error": decision.get("error"),
            "orders": linked_orders,
            "fills": linked_fills,
        })
    return {"run_id": run_id, "decisions": decisions}


def audit_csv(audit):
    """Serialize the stable, explicitly allow-listed audit columns."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for decision in audit["decisions"]:
        probabilities = decision.get("probabilities", {})
        inputs = decision.get("input", {})
        writer.writerow({
            "minute": decision.get("minute"),
            "symbol": decision.get("symbol"),
            "action": decision.get("action"),
            **{f"{name.lower()}_probability": probabilities.get(name)
               for name in ("BUY", "HOLD", "SELL", "ABSTAIN")},
            **{name: inputs.get(name) for name in (
                "sma20", "sma60", "trend", "momentum_30", "volatility_20",
                "relative_volume", "position_state", "position_quantity", "minutes_remaining",
            )},
            **{name: decision.get(name) for name in (
                "input_version", "question_version", "requested_model", "returned_model",
                "explanation", "error",
            )},
            "order_ids": ";".join(item["id"] for item in decision["orders"]),
            "fill_ids": ";".join(item["id"] for item in decision["fills"]),
        })
    return output.getvalue()
