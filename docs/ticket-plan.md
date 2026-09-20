# Draft implementation tickets

Status: proposed after Grill Me; not yet approved or published.

Each ticket is a small vertical slice intended to take a human a few hours. Each implementation cycle must follow red → green at the agreed public seam and avoid tests against private helpers.

## 01. Boot the local simulator application

Blocked by: None

What it delivers: A user can start the single-user Python application, open one native HTML page, and see configuration/health status without exposing secrets.

Acceptance:
- A process-level test starts the app and verifies the public health/page responses.
- Missing Alpaca or TypeSafe configuration is reported safely without printing secret values.

## 02. Fetch and reuse an immutable historical market snapshot

Blocked by: 01

What it delivers: Given a completed trading date, the application fetches AAPL, MSFT, and NVDA one-minute regular-session bars from Alpaca or reuses an identical cached snapshot.

Acceptance:
- The historical-data seam returns validated, ordered bars plus source metadata and a stable digest.
- Holidays, future/incomplete dates, gaps, malformed responses, and unavailable data fail explicitly.
- Repeating the request reuses the matching cached snapshot.

## 03. Create immutable runs and append-only records

Blocked by: 01

What it delivers: The application creates a unique run, appends timestamped events to SQLite, reports status/progress, and never overwrites a completed run.

Acceptance:
- The run-store seam supports create, append, progress, complete, fail, list, and read operations.
- A rerun creates a distinct ID; completed records cannot be mutated.
- Schema initialization and transaction rollback are verified through the public store interface.

## 04. Produce the replaceable `trend_momentum_v1` strategy input

Blocked by: 02

What it delivers: After 60 warm-up minutes, each stock/minute yields a versioned strategy snapshot containing SMA20/SMA60 trend, 30-minute momentum, 20-minute volatility, relative volume, position state, and minutes remaining.

Acceptance:
- The strategy seam accepts public market/account inputs and returns a typed, versioned decision request.
- No request is produced during warm-up or from incomplete/future bars.
- A second strategy can be substituted through the same seam without changing callers.

## 05. Execute a costed buy-and-hold benchmark

Blocked by: 02, 03

What it delivers: A completed historical day produces a persisted buy-and-hold result using $100,000, the shared cash pool, a 10%-per-stock cap, next-minute-open fills, 2-bps adverse execution cost, sell-side regulatory fees, and forced close.

Acceptance:
- The simulation seam returns a reconciled completed run with orders, fills, fees, positions, equity points, and net P&L.
- Cash never becomes negative; exposure and whole-share constraints hold.
- Ledger totals reconcile independently to ending cash/equity.

## 06. Run a simulation as a background job through HTTP

Blocked by: 03, 05

What it delivers: The dashboard can create a buy-and-hold run, poll progress, list immutable runs, and read completion/failure through public HTTP endpoints while the work continues in the background.

Acceptance:
- HTTP tests verify create, duplicate submission behavior, progress, list, and result responses.
- Restarting the web process does not corrupt completed runs; interrupted in-progress runs become explicit failures rather than false successes.

## 07. Add the deterministic SMA20/SMA60 comparison

Blocked by: 04, 05

What it delivers: The same historical snapshot and execution engine produce a persisted moving-average crossover result with no decisions during warm-up and equal allocation/cost rules.

Acceptance:
- Known bar examples independently establish crossover BUY/HOLD/SELL outcomes.
- Signals use completed bars and fills occur no earlier than the next minute.
- The run reconciles through the same simulation seam as buy-and-hold.

## 08. Obtain and persist one bounded JEV stock decision

Blocked by: 03, 04

What it delivers: For one stock/minute, the pinned JEV model receives only the compact strategy snapshot and returns a validated BUY/HOLD/SELL/ABSTAIN distribution that is persisted with model/question/input versions.

Acceptance:
- A fake decision provider drives public-seam tests; one narrow live smoke test is optional when credentials are present.
- Timeouts, invalid schemas, unexpected options/models, and exhausted bounded retries become ABSTAIN with an error record.
- JEV never receives API keys, performs arithmetic, or creates an order.

## 09. Evaluate all three stocks independently per minute

Blocked by: 08

What it delivers: A minute snapshot triggers separate concurrent JEV calls for AAPL, MSFT, and NVDA from the same portfolio state, then returns one complete three-stock decision set.

Acceptance:
- One slow/failing stock call does not change or suppress valid decisions for the other stocks.
- Results remain associated with the correct stock regardless of completion order.
- No portfolio mutation occurs until the complete decision set is validated.

## 10. Complete a full-day JEV simulation

Blocked by: 05, 09

What it delivers: The background simulator processes every eligible post-warm-up minute as fast as JEV responds, applies the default action policy, persists all evidence/actions/fills, and liquidates remaining positions before close.

Acceptance:
- BUY opens a flat stock toward its 10%-of-equity target; repeated BUY while long is unavailable; SELL closes; HOLD/ABSTAIN does nothing.
- Simultaneous valid buys are applied deterministically from the shared minute snapshot without violating cash or exposure limits.
- Duplicate minute processing cannot create duplicate decisions or orders.
- Ending positions are flat and persisted accounting reconciles.

## 11. Show run creation and progress on the page

Blocked by: 06

What it delivers: The native single page offers a historical-date form defaulting to the latest available date, starts a run, shows progress/failure, and lists immutable completed runs.

Acceptance:
- Browser-facing behavior is verified through HTTP/HTML contracts, not DOM implementation details.
- The page remains usable by keyboard, labels paper trading clearly, and never asks for API keys.

## 12. Compare JEV, SMA, and buy-and-hold results

Blocked by: 07, 10

What it delivers: A completed run exposes and displays net profit, return, maximum drawdown, trade count, total costs, per-stock contribution, benchmark differences, and an accessible equity curve for all three methods.

Acceptance:
- The read-model seam derives all metrics from persisted run data without calling JEV.
- Worked examples independently verify P&L, return, costs, and maximum drawdown.
- All methods use the same source digest, starting cash, allocation caps, and execution/fee versions.

## 13. Inspect and export the JEV audit trail

Blocked by: 06, 10

What it delivers: The result page filters JEV decisions by stock/action/minute and shows probabilities, feature inputs, deterministic explanation, errors, linked orders/fills, and CSV downloads.

Acceptance:
- The read-model/CSV seams preserve exact stored values and stable column meanings.
- CSV contains no credentials or secret headers.
- Dashboard analysis of a completed run performs zero JEV calls.

## 14. Assemble the final one-page experience

Blocked by: 11, 12, 13

What it delivers: One responsive, accessible native HTML/CSS/JavaScript page combines run creation, progress, completed-run selection, comparison summary, equity curve, fills/fees, and decision audit log.

Acceptance:
- A user can complete the entire workflow without a command line after server startup.
- Stale/loading/error states retain the last valid data and communicate status accessibly.
- No frontend framework, router, component kit, or chart dependency is added.

## 15. Verify a reproducible end-to-end historical run

Blocked by: 14

What it delivers: A documented real run for one completed date fetches Alpaca data, calls pinned JEV, persists all three methods, renders the dashboard, and exports CSV with captured verification evidence.

Acceptance:
- Real tool output records run ID, date, source digest, requested/returned JEV model, strategy/fee/execution versions, final metrics, and passing checks.
- A second run using the cached market snapshot proves source reuse while remaining an immutable distinct run.
- Setup documentation covers environment variables, startup, limitations, and the fact that results are hypothetical.

## Dependency frontier

- Start immediately: 01
- After 01: 02 and 03 in parallel
- After 02: 04
- After 02 + 03: 05
- After 04 + 05: 07
- After 03 + 04: 08
- After 03 + 05: 06
- After 08: 09
- After 05 + 09: 10
- After 06: 11
- After 07 + 10: 12
- After 06 + 10: 13
- After 11 + 12 + 13: 14
- After 14: 15
