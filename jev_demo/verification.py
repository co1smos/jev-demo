"""Run and summarize the real historical acceptance check."""

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from .__main__ import RunApplication, execute_run, handler_for
from .decision import TypeSafeDecisionProvider
from .historical_data import AlpacaHistoricalData
from .run_store import RunStore


def _get(base_url, path):
    with urlopen(base_url + path, timeout=2) as response:
        return response.read()


def verification_evidence(base_url, first_run_id, second_run_id):
    page = _get(base_url, "/").decode()
    runs = [json.loads(_get(base_url, f"/api/runs/{run_id}"))
            for run_id in (first_run_id, second_run_id)]
    snapshots = [
        next(record["data"] for record in run["records"] if record["kind"] == "market_snapshot")
        for run in runs
    ]
    decisions = [decision for run in runs for decision in run["result"]["decisions"]]
    requested = {decision["requested_model"] for decision in decisions}
    returned = {decision["returned_model"] for decision in decisions
                if decision["returned_model"] is not None}
    strategies = {decision["input_version"] for decision in decisions}
    comparisons = [json.loads(_get(base_url, f"/api/runs/{run['id']}/comparison"))
                   for run in runs]
    audits = [json.loads(_get(base_url, f"/api/runs/{run['id']}/audit")) for run in runs]
    csv_exports = []
    for run in runs:
        body = _get(base_url, f"/api/runs/{run['id']}/audit.csv")
        csv_exports.append({
            "run_id": run["id"],
            "row_count": sum(1 for _ in csv.DictReader(io.StringIO(body.decode()))),
            "sha256": hashlib.sha256(body).hexdigest(),
        })
    evidence = {
        "date": runs[0]["request"]["trading_date"],
        "source_digest": snapshots[0]["source_digest"],
        "requested_jev_model": next(iter(requested)) if len(requested) == 1 else sorted(requested),
        "returned_jev_model": next(iter(returned)) if len(returned) == 1 else sorted(returned, key=str),
        "strategy_version": next(iter(strategies)) if len(strategies) == 1 else sorted(strategies),
        "fee_version": runs[0]["result"]["fee_version"],
        "execution_version": runs[0]["result"]["execution_model_version"],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "csv_exports": csv_exports,
        "runs": [{
            "run_id": run["id"],
            "source_reused": snapshot["reused"],
            "final_metrics": [
                {key: value for key, value in method.items() if key != "equity_curve"}
                for method in result["methods"]
            ],
        } for run, snapshot, result in zip(runs, snapshots, comparisons)],
        "checks": {
            "distinct_immutable_runs": first_run_id != second_run_id
            and all(run["status"] == "completed" for run in runs),
            "first_run_fetched_source": snapshots[0]["reused"] is False,
            "second_run_reused_source": snapshots[1]["reused"] is True,
            "source_digest_matches": snapshots[0]["source_digest"] == snapshots[1]["source_digest"],
            "pinned_jev_model_returned": len(requested) == len(returned) == 1 and requested == returned,
            "three_methods_persisted": all(
                [method["method"] for method in result["methods"]]
                == ["jev", "sma20_sma60", "buy_and_hold"]
                for result in comparisons
            ),
            "dashboard_rendered": all(run["status"] == "completed" for run in runs)
            and all(result["run_id"] == run["id"] for run, result in zip(runs, comparisons))
            and all(audit["run_id"] == run["id"] for run, audit in zip(runs, audits))
            and 'id="comparison-summary"' in page and 'id="audit"' in page,
            "csv_exported": all(export["row_count"] > 0 for export in csv_exports),
        },
    }
    if not all(evidence["checks"].values()):
        raise RuntimeError(f"verification failed: {evidence['checks']}")
    return evidence


def _serve(store, trading_date):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        handler_for(RunApplication(store, lambda *_: None), lambda: trading_date),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trading_date")
    parser.add_argument("--database")
    parser.add_argument("--cache")
    parser.add_argument("--output")
    args = parser.parse_args()
    if not all(os.environ.get(name) for name in (
        "ALPACA_API_KEY", "ALPACA_API_SECRET", "TYPESAFE_API_KEY"
    )):
        parser.error("ALPACA_API_KEY, ALPACA_API_SECRET, and TYPESAFE_API_KEY are required")

    with tempfile.TemporaryDirectory() as directory:
        database = Path(args.database or Path(directory) / "verification.db")
        cache = Path(args.cache or Path(directory) / "cache")
        store = RunStore(database)
        data = AlpacaHistoricalData(
            os.environ["ALPACA_API_KEY"], os.environ["ALPACA_API_SECRET"], cache
        )
        provider = TypeSafeDecisionProvider(os.environ["TYPESAFE_API_KEY"])
        run_ids = []
        for _ in range(2):
            run_id = store.create({"trading_date": args.trading_date, "method": "jev"})
            store.progress(run_id, 0, 2)
            execute_run(store, run_id, args.trading_date, data, provider)
            run_ids.append(run_id)
        server, thread = _serve(store, args.trading_date)
        try:
            evidence = verification_evidence(
                f"http://127.0.0.1:{server.server_port}", *run_ids
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
        output = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        if args.output:
            Path(args.output).write_text(output)
        print(output, end="")


if __name__ == "__main__":
    main()
