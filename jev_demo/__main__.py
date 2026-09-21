import json
import os
import re
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .audit import audit_csv, read_audit
from .decision import TypeSafeDecisionProvider
from .historical_data import AlpacaHistoricalData
from .run_store import RunStore
from .simulation import SimulationRequest, run_simulation


def latest_historical_date():
    return AlpacaHistoricalData(
        os.environ.get("ALPACA_API_KEY"),
        os.environ.get("ALPACA_API_SECRET"),
        Path(os.environ.get("JEV_DEMO_CACHE", ".jev-demo-cache")),
    ).latest_completed_date()


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
        request = {**request, "method": "jev"}
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
                run_simulation(
                    SimulationRequest(request["trading_date"], "jev"),
                    snapshot,
                    self.store,
                    run_id=run_id,
                    decision_provider=TypeSafeDecisionProvider(os.environ.get("TYPESAFE_API_KEY")),
                )
            except Exception as error:
                try:
                    self.store.fail(run_id, error)
                except ValueError:
                    pass

        threading.Thread(target=work, daemon=True).start()


def handler_for(application, latest_date=latest_historical_date):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _csv(self, value, filename):
            body = value.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
            url = urlsplit(self.path)
            path = url.path
            config = configuration()
            if path == "/health":
                self._json(200, {
                    "status": "ok" if "missing" not in config.values() else "configuration_required",
                    "configuration": config,
                })
                return
            if path == "/api/runs":
                self._json(200, application.store.list())
                return
            audit_match = re.fullmatch(r"/api/runs/([^/]+)/audit(\.csv)?", path)
            if audit_match:
                filters = {key: values[-1] for key, values in parse_qs(url.query).items()
                           if key in ("symbol", "action", "minute")}
                try:
                    audit = read_audit(application.store, audit_match.group(1), **filters)
                except KeyError:
                    self._json(404, {"error": "run not found"})
                    return
                except ValueError as error:
                    self._json(409, {"error": str(error)})
                    return
                if audit_match.group(2):
                    self._csv(audit_csv(audit), f"jev-audit-{audit_match.group(1)}.csv")
                else:
                    self._json(200, audit)
                return
            match = re.fullmatch(r"/api/runs/([^/]+)(/result)?", path)
            if match:
                try:
                    run = application.store.read(match.group(1))
                except KeyError:
                    self._json(404, {"error": "run not found"})
                    return
                self._json(202 if match.group(2) and run["status"] == "running" else 200, run)
                return
            if path == "/":
                status = "Ready" if "missing" not in config.values() else "Configuration required"
                try:
                    default_date = latest_date()
                except ValueError:
                    default_date = ""
                body = f'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JEV Simulator</title>
<style>
body{{font:1rem system-ui;max-width:48rem;margin:auto;padding:1rem;line-height:1.5}}
form{{display:flex;gap:.75rem;align-items:end;flex-wrap:wrap}}
label{{display:block;font-weight:600}}button,input,select{{font:inherit;padding:.5rem}}
button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{{outline:3px solid #165dff;outline-offset:2px}}
.notice{{border-left:.35rem solid #b45309;padding:.5rem 1rem;background:#fff7ed}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top}}
pre{{white-space:pre-wrap;margin:0}}
</style>
<h1>JEV Simulator</h1>
<p class="notice"><strong>Historical paper trading only.</strong> No live orders or financial advice.</p>
<p>Server status: {status}. Alpaca: {config['alpaca']}. TypeSafe: {config['typesafe']}.</p>
<main>
  <h2>Start a run</h2>
  <form id="run-form">
    <div><label for="trading-date">Trading date</label>
    <input type="date" id="trading-date" name="trading_date" value="{default_date}" required></div>
    <button type="submit">Run simulation</button>
  </form>
  <p id="run-status" role="status" aria-live="polite">No run in progress.</p>
  <h2>Completed runs</h2>
  <ul id="completed-runs"><li>Loading…</li></ul>
  <section id="audit" hidden>
    <h2>JEV decision audit</h2>
    <form id="audit-filters">
      <div><label for="audit-symbol">Stock</label><select id="audit-symbol" name="symbol"><option value="">All</option><option>AAPL</option><option>MSFT</option><option>NVDA</option></select></div>
      <div><label for="audit-action">Action</label><select id="audit-action" name="action"><option value="">All</option><option>BUY</option><option>HOLD</option><option>SELL</option><option>ABSTAIN</option></select></div>
      <div><label for="audit-minute">Minute</label><input id="audit-minute" name="minute" type="text" placeholder="2026-09-18T14:30:00Z"></div>
      <button type="submit">Filter</button><a id="audit-csv" href="#">Download CSV</a>
    </form>
    <p id="audit-count" role="status"></p>
    <table><thead><tr><th>Minute / stock</th><th>Decision evidence</th><th>Explanation / execution</th></tr></thead><tbody id="audit-rows"></tbody></table>
  </section>
</main>
<script>
const form=document.querySelector("#run-form"),status=document.querySelector("#run-status"),list=document.querySelector("#completed-runs"),button=form.querySelector("button"),audit=document.querySelector("#audit"),filters=document.querySelector("#audit-filters"),rows=document.querySelector("#audit-rows"),count=document.querySelector("#audit-count"),csv=document.querySelector("#audit-csv");let selectedRun;
async function request(url,options){{const response=await fetch(url,options);const data=await response.json();if(!response.ok)throw new Error(data.error||"Request failed");return data}}
function show(run){{if(run.status==="running"){{const p=run.progress;status.textContent=`Run in progress: ${{p.current}} of ${{p.total}} steps complete.`}}else if(run.status==="failed")status.textContent=`Run failed: ${{run.error}}`;else status.textContent="Run completed."}}
async function completedRuns(){{try{{const runs=await request("/api/runs");const completed=runs.filter(run=>run.status==="completed");list.replaceChildren(...(completed.length?completed.map(run=>{{const item=document.createElement("li"),pick=document.createElement("button");pick.type="button";pick.textContent=`${{run.request.trading_date}} — completed ${{new Date(run.updated_at).toLocaleString()}}`;pick.addEventListener("click",()=>selectRun(run.id));item.append(pick);return item}}):[Object.assign(document.createElement("li"),{{textContent:"No completed runs yet."}})]))}}catch(error){{list.textContent=error.message}}}}
function auditUrl(extension=""){{const query=new URLSearchParams(new FormData(filters));for(const [key,value] of [...query])if(!value)query.delete(key);return `/api/runs/${{selectedRun}}/audit${{extension}}?${{query}}`}}
async function loadAudit(){{try{{const data=await request(auditUrl());rows.replaceChildren(...data.decisions.map(decision=>{{const row=document.createElement("tr");for(const value of [`${{decision.minute}}\n${{decision.symbol}}`,JSON.stringify({{action:decision.action,probabilities:decision.probabilities,input:decision.input,error:decision.error}},null,2),JSON.stringify({{explanation:decision.explanation,orders:decision.orders,fills:decision.fills}},null,2)]){{const cell=document.createElement("td"),pre=document.createElement("pre");pre.textContent=value;cell.append(pre);row.append(cell)}}return row}}));count.textContent=`${{data.decisions.length}} decision${{data.decisions.length===1?"":"s"}}.`;csv.href=auditUrl(".csv")}}catch(error){{count.textContent=error.message}}}}
function selectRun(id){{selectedRun=id;audit.hidden=false;loadAudit()}}
filters.addEventListener("submit",event=>{{event.preventDefault();loadAudit()}});
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
