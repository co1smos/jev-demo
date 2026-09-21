import json
import os
import re
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .historical_data import AlpacaHistoricalData
from .run_store import RunStore
from .simulation import SimulationRequest, run_buy_and_hold


def latest_historical_date():
    candidate = date.today() - timedelta(days=1)
    while candidate.weekday() > 4:
        candidate -= timedelta(days=1)
    return candidate.isoformat()


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
                body = f'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JEV Simulator</title>
<style>
body{{font:1rem system-ui;max-width:48rem;margin:auto;padding:1rem;line-height:1.5}}
form{{display:flex;gap:.75rem;align-items:end;flex-wrap:wrap}}
label{{display:block;font-weight:600}}button,input{{font:inherit;padding:.5rem}}
button:focus-visible,input:focus-visible{{outline:3px solid #165dff;outline-offset:2px}}
.notice{{border-left:.35rem solid #b45309;padding:.5rem 1rem;background:#fff7ed}}
</style>
<h1>JEV Simulator</h1>
<p class="notice"><strong>Historical paper trading only.</strong> No live orders or financial advice.</p>
<p>Server status: {status}. Alpaca: {config['alpaca']}. TypeSafe: {config['typesafe']}.</p>
<main>
  <h2>Start a run</h2>
  <form id="run-form">
    <div><label for="trading-date">Trading date</label>
    <input type="date" id="trading-date" name="trading_date" value="{latest_historical_date()}" required></div>
    <button type="submit">Run simulation</button>
  </form>
  <p id="run-status" role="status" aria-live="polite">No run in progress.</p>
  <h2>Completed runs</h2>
  <ul id="completed-runs"><li>Loading…</li></ul>
</main>
<script>
const form=document.querySelector("#run-form"),status=document.querySelector("#run-status"),list=document.querySelector("#completed-runs"),button=form.querySelector("button");
async function request(url,options){{const response=await fetch(url,options);const data=await response.json();if(!response.ok)throw new Error(data.error||"Request failed");return data}}
function show(run){{if(run.status==="running"){{const p=run.progress;status.textContent=`Run in progress: ${{p.current}} of ${{p.total}} steps complete.`}}else if(run.status==="failed")status.textContent=`Run failed: ${{run.error}}`;else status.textContent="Run completed."}}
async function completedRuns(){{try{{const runs=await request("/api/runs");const completed=runs.filter(run=>run.status==="completed");list.replaceChildren(...(completed.length?completed.map(run=>{{const item=document.createElement("li");item.textContent=`${{run.request.trading_date}} — completed ${{new Date(run.updated_at).toLocaleString()}}`;return item}}):[Object.assign(document.createElement("li"),{{textContent:"No completed runs yet."}})]))}}catch(error){{list.textContent=error.message}}}}
async function poll(id){{try{{const run=await request(`/api/runs/${{id}}`);show(run);if(run.status==="running")setTimeout(()=>poll(id),1000);else{{button.disabled=false;completedRuns()}}}}catch(error){{status.textContent=error.message;button.disabled=false}}}}
form.addEventListener("submit",async event=>{{event.preventDefault();button.disabled=true;status.textContent="Starting run…";try{{const run=await request("/api/runs",{{method:"POST",headers:{{"Content-Type":"application/json","Idempotency-Key":crypto.randomUUID()}},body:JSON.stringify({{trading_date:form.trading_date.value}})}});show(run);poll(run.id)}}catch(error){{status.textContent=`Could not start run: ${{error.message}}`;button.disabled=false}}}});
completedRuns();
</script>
</html>'''.encode()
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
