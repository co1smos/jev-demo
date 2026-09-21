import json
import os
import re
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .historical_data import AlpacaHistoricalData
from .run_store import RunStore
from .simulation import SimulationRequest, run_buy_and_hold


def configuration():
    return {
        "alpaca": "configured"
        if os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_API_SECRET")
        else "missing",
        "typesafe": "configured" if os.environ.get("TYPESAFE_API_KEY") else "missing",
    }


class RunApplication:
    def __init__(self, store, submit=None):
        self.store = store
        self.store.fail_running("web process restarted before the run completed")
        self.submit = submit or self._submit

    def create(self, request, idempotency_key=None):
        if not isinstance(request, dict) or set(request) != {"trading_date"}:
            raise ValueError("trading_date is required")
        date.fromisoformat(request["trading_date"])
        request = {**request, "method": "buy_and_hold"}
        run_id, created = self.store.create_once(request, idempotency_key)
        if created:
            self.store.progress(run_id, 0, 2)
            self.submit(run_id, request)
        return self.store.read(run_id), created

    def _submit(self, run_id, request):
        def work():
            try:
                data = AlpacaHistoricalData(
                    os.environ.get("ALPACA_API_KEY"),
                    os.environ.get("ALPACA_API_SECRET"),
                    Path(os.environ.get("JEV_DEMO_CACHE", ".jev-demo-cache")),
                )
                snapshot = data.snapshot(request["trading_date"]).snapshot
                self.store.progress(run_id, 1, 2)
                run_buy_and_hold(SimulationRequest(request["trading_date"]), snapshot, self.store, run_id)
            except Exception as error:
                try:
                    self.store.fail(run_id, error)
                except ValueError:
                    pass

        threading.Thread(target=work, daemon=True).start()


def handler_for(application):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/api/runs":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                run, created = application.create(request, self.headers.get("Idempotency-Key"))
                self._json(202 if created else 200, run)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                self._json(400, {"error": str(error)})

        def do_GET(self):
            config = configuration()
            if self.path == "/health":
                self._json(200, {
                    "status": "ok" if "missing" not in config.values() else "configuration_required",
                    "configuration": config,
                })
                return
            if self.path == "/api/runs":
                self._json(200, application.store.list())
                return
            match = re.fullmatch(r"/api/runs/([^/]+)(/result)?", self.path)
            if match:
                try:
                    run = application.store.read(match.group(1))
                except KeyError:
                    self._json(404, {"error": "run not found"})
                    return
                self._json(202 if match.group(2) and run["status"] == "running" else 200, run)
                return
            if self.path == "/":
                status = "Ready" if "missing" not in config.values() else "Configuration required"
                body = (
                    "<!doctype html><html lang=en><meta charset=utf-8>"
                    "<meta name=viewport content='width=device-width,initial-scale=1'>"
                    f"<title>JEV Simulator</title><h1>JEV Simulator</h1><h2>{status}</h2>"
                    f"<p>Alpaca: {config['alpaca']}</p><p>TypeSafe: {config['typesafe']}</p>"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def log_message(self, format, *args):
            pass

    return Handler


if __name__ == "__main__":
    port = int(os.environ.get("JEV_DEMO_PORT", "8000"))
    store = RunStore(os.environ.get("JEV_DEMO_DATABASE", "jev-demo.db"))
    print(f"JEV Simulator listening on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), handler_for(RunApplication(store))).serve_forever()
