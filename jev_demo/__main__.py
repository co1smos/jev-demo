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
from .read_model import comparison
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
                    SimulationRequest(request["trading_date"], "sma20_sma60", run_id),
                    snapshot,
                    self.store,
                )
                run_simulation(
                    SimulationRequest(request["trading_date"], "buy_and_hold", run_id),
                    snapshot,
                    self.store,
                )
                run_simulation(
                    SimulationRequest(request["trading_date"], "jev", run_id),
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
            comparison_match = re.fullmatch(r"/api/runs/([^/]+)/comparison", path)
            if comparison_match:
                try:
                    self._json(200, comparison(application.store, comparison_match.group(1)))
                except KeyError:
                    self._json(404, {"error": "run not found"})
                except ValueError as error:
                    self._json(409, {"error": str(error)})
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
table{{border-collapse:collapse;width:100%;display:block;overflow:auto}}th,td{{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top}}
#comparison-summary th,#comparison-summary td{{text-align:right}}#comparison-summary th:first-child,#comparison-summary td:first-child{{text-align:left}}
pre{{white-space:pre-wrap;margin:0}}
svg{{width:100%;height:12rem;border:1px solid #ccc}}
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
  <p id="runs-status" role="status" aria-live="polite"></p>
  <ul id="completed-runs"><li>Loading…</li></ul>
  <p id="result-status" role="status" aria-live="polite">Select a completed run to inspect it.</p>
  <section id="audit" aria-busy="false" hidden>
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
  <section id="comparison-summary" aria-busy="false" hidden>
    <h2>Method comparison</h2>
    <table><caption>Method comparison</caption><thead><tr><th>Method</th><th>Net profit</th><th>Return</th><th>Max drawdown</th><th>Trades</th><th>Total costs</th><th>vs buy-and-hold</th></tr></thead><tbody id="comparison-body"></tbody></table>
    <h3>Equity curve</h3>
    <p id="equity-summary"></p>
    <svg id="equity-chart" viewBox="0 0 600 200" aria-hidden="true"></svg>
    <details id="equity-data"><summary>Show exact equity data</summary><table><caption>Equity by method and time</caption><thead><tr><th>Method</th><th>Time</th><th>Equity</th></tr></thead><tbody></tbody></table></details>
    <h3>Per-stock contribution</h3>
    <table><caption>Per-stock contribution</caption><thead><tr><th>Method</th><th>Stock</th><th>Contribution</th></tr></thead><tbody id="contribution-body"></tbody></table>
    <h3>JEV execution</h3>
    <table><caption>JEV fills</caption><thead><tr><th>Time</th><th>Stock</th><th>Side</th><th>Quantity</th><th>Price</th><th>Execution cost</th></tr></thead><tbody id="fills-body"></tbody></table>
    <table><caption>JEV fees</caption><thead><tr><th>Fee</th><th>Amount</th></tr></thead><tbody id="fees-body"></tbody></table>
    <table><caption>JEV ending positions</caption><thead><tr><th>Stock</th><th>Quantity</th><th>Realized P&amp;L</th></tr></thead><tbody id="positions-body"></tbody></table>
  </section>
</main>
<script>
const form=document.querySelector("#run-form"),status=document.querySelector("#run-status"),runsStatus=document.querySelector("#runs-status"),resultStatus=document.querySelector("#result-status"),list=document.querySelector("#completed-runs"),button=form.querySelector("button"),audit=document.querySelector("#audit"),filters=document.querySelector("#audit-filters"),rows=document.querySelector("#audit-rows"),count=document.querySelector("#audit-count"),csv=document.querySelector("#audit-csv"),summary=document.querySelector("#comparison-summary");let selectedRun,hasResult=false,lastProgress="No progress received yet.";
const money=new Intl.NumberFormat(undefined,{{style:"currency",currency:"USD"}}),percent=new Intl.NumberFormat(undefined,{{style:"percent",maximumFractionDigits:2}});
async function request(url,options){{const response=await fetch(url,options);const data=await response.json();if(!response.ok)throw new Error(data.error||"Request failed");return data}}
function show(run){{if(run.status==="running"){{const p=run.progress;lastProgress=`Run in progress: ${{p.current}} of ${{p.total}} steps complete.`;status.textContent=lastProgress}}else if(run.status==="failed")status.textContent=`Run failed: ${{run.error}}`;else status.textContent="Run completed."}}
function cell(row,value){{const item=document.createElement("td");item.textContent=value;row.append(item)}}
function auditUrl(id,extension=""){{const query=new URLSearchParams(new FormData(filters));for(const [key,value] of [...query])if(!value)query.delete(key);return `/api/runs/${{id}}/audit${{extension}}?${{query}}`}}
async function loadAudit(id=selectedRun){{audit.setAttribute("aria-busy","true");count.textContent="Loading decisions…";try{{const data=await request(auditUrl(id));if(id!==selectedRun)return;rows.replaceChildren(...data.decisions.map(decision=>{{const row=document.createElement("tr");for(const value of [`${{decision.minute}}\n${{decision.symbol}}`,JSON.stringify({{action:decision.action,probabilities:decision.probabilities,input:decision.input,error:decision.error}},null,2),JSON.stringify({{explanation:decision.explanation,orders:decision.orders,fills:decision.fills}},null,2)]){{const cell=document.createElement("td"),pre=document.createElement("pre");pre.textContent=value;cell.append(pre);row.append(cell)}}return row}}));count.textContent=`${{data.decisions.length}} decision${{data.decisions.length===1?"":"s"}}.`;csv.href=auditUrl(id,".csv")}}catch(error){{if(id===selectedRun)count.textContent=`Could not refresh decisions: ${{error.message}} Showing the last loaded data.`}}finally{{if(id===selectedRun)audit.setAttribute("aria-busy","false")}}}}
async function showComparison(id){{summary.setAttribute("aria-busy","true");resultStatus.textContent="Loading selected run…";try{{const [data,run]=await Promise.all([request(`/api/runs/${{id}}/comparison`),request(`/api/runs/${{id}}`)]);if(id!==selectedRun)return;const body=document.querySelector("#comparison-body"),contributions=document.querySelector("#contribution-body"),equities=document.querySelector("#equity-data tbody"),svg=document.querySelector("#equity-chart"),fills=document.querySelector("#fills-body"),fees=document.querySelector("#fees-body"),positions=document.querySelector("#positions-body");body.replaceChildren();contributions.replaceChildren();equities.replaceChildren();svg.replaceChildren();fills.replaceChildren();fees.replaceChildren();positions.replaceChildren();const colors=["#165dff","#b45309","#047857"],all=data.methods.flatMap(method=>method.equity_curve.map(point=>Number(point.equity))),low=Math.min(...all),high=Math.max(...all),span=high-low||1;data.methods.forEach((method,index)=>{{const row=document.createElement("tr");cell(row,method.method);cell(row,money.format(method.net_profit));cell(row,percent.format(method.return));cell(row,percent.format(method.maximum_drawdown_return));cell(row,method.trade_count);cell(row,money.format(method.total_costs));cell(row,money.format(method.difference_from_buy_and_hold.net_profit));body.append(row);Object.entries(method.per_stock_contribution).forEach(([symbol,value])=>{{const contribution=document.createElement("tr");cell(contribution,method.method);cell(contribution,symbol);cell(contribution,money.format(value));contributions.append(contribution)}});method.equity_curve.forEach(point=>{{const exact=document.createElement("tr");cell(exact,method.method);cell(exact,point.timestamp);cell(exact,money.format(point.equity));equities.append(exact)}});const line=document.createElementNS("http://www.w3.org/2000/svg","polyline"),last=Math.max(method.equity_curve.length-1,1);line.setAttribute("points",method.equity_curve.map((point,i)=>`${{i/last*600}},${{190-(Number(point.equity)-low)/span*180}}`).join(" "));line.setAttribute("fill","none");line.setAttribute("stroke",colors[index]);line.setAttribute("stroke-width","3");svg.append(line)}});for(const fill of run.result.fills){{const row=document.createElement("tr");for(const value of [fill.timestamp,fill.symbol,fill.side,fill.quantity,money.format(fill.price),money.format(fill.execution_cost)])cell(row,value);fills.append(row)}}for(const fee of run.result.fees){{const row=document.createElement("tr");cell(row,fee.kind);cell(row,money.format(fee.amount));fees.append(row)}}for(const position of run.result.positions){{const row=document.createElement("tr");cell(row,position.symbol);cell(row,position.quantity);cell(row,money.format(position.realized_pnl));positions.append(row)}}document.querySelector("#equity-summary").textContent=`Equity ranges from ${{money.format(low)}} to ${{money.format(high)}}. Exact values follow.`;summary.hidden=false;hasResult=true;resultStatus.textContent=`Showing completed run for ${{run.request.trading_date}}.`}}catch(error){{if(id===selectedRun)resultStatus.textContent=`Could not load selected run: ${{error.message}}${{hasResult?" Showing the last loaded data.":""}}`}}finally{{if(id===selectedRun)summary.setAttribute("aria-busy","false")}}}}
function selectRun(id){{selectedRun=id;audit.hidden=false;loadAudit(id);showComparison(id)}}
filters.addEventListener("submit",event=>{{event.preventDefault();loadAudit()}});
async function completedRuns(){{runsStatus.textContent="Loading completed runs…";try{{const runs=await request("/api/runs");const completed=runs.filter(run=>run.status==="completed"&&run.request.method==="jev");list.replaceChildren(...(completed.length?completed.map(run=>{{const item=document.createElement("li"),select=document.createElement("button");select.type="button";select.textContent=`${{run.request.trading_date}} — completed ${{new Date(run.updated_at).toLocaleString()}}`;select.addEventListener("click",()=>selectRun(run.id));item.append(select);return item}}):[Object.assign(document.createElement("li"),{{textContent:"No completed runs yet."}})]));runsStatus.textContent=""}}catch(error){{runsStatus.textContent=`Could not refresh completed runs: ${{error.message}} Showing the last loaded data.`}}}}
async function poll(id){{try{{const run=await request(`/api/runs/${{id}}`);show(run);if(run.status==="running")setTimeout(()=>poll(id),1000);else{{button.disabled=false;completedRuns()}}}}catch(error){{status.textContent=`${{lastProgress}} Could not refresh progress: ${{error.message}} Last known progress is retained; retrying.`;setTimeout(()=>poll(id),1000)}}}}
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
