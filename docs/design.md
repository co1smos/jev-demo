# JEV historical paper-trading simulator — agreed v1 design

## Purpose

Build a visible, educational simulator that answers a narrow question: can JEV-directed trades make money on a completed US trading day after plausible retail trading costs?

This is historical paper trading, not live trading, financial advice, or proof that a strategy will remain profitable.

## Run lifecycle

1. The user selects any completed trading date; the latest available date is the default.
2. A background job fetches or reuses cached Alpaca one-minute bars for AAPL, MSFT, and NVDA.
3. The account starts with $100,000 cash and no positions.
4. The first 60 regular-session minutes are warm-up only.
5. For every later completed minute, three separate JEV calls run concurrently from the same immutable portfolio snapshot—one call per stock.
6. Each call returns BUY, HOLD, SELL, or ABSTAIN with its probability distribution.
7. Deterministic code validates all three results and applies their orders together.
8. BUY targets 10% of current portfolio equity only when that stock is flat; SELL closes the entire position; HOLD and ABSTAIN make no change. No leverage, shorts, fractional shares, or repeated additions.
9. Orders fill at the next minute's open with a fixed adverse 2-basis-point execution cost. Generic Fidelity/E*TRADE-like fees use $0 online-stock commission plus applicable sell-side SEC/FINRA fees.
10. Remaining positions are forcibly liquidated before the session ends.
11. The run continuously persists inputs, JEV outputs, actions, orders, fills, fees, positions, and equity to SQLite.
12. After completion, the dashboard analyzes stored data without calling JEV again.

## Default strategy

`trend_momentum_v1` is the only built-in strategy in v1, behind a replaceable strategy seam.

For each stock it supplies JEV with public-market-data-derived values available from historical or future real-time APIs:

- SMA20 versus SMA60 trend;
- 30-minute return momentum;
- 20-minute volatility;
- relative volume;
- current position state; and
- minutes remaining in the regular session.

JEV performs no arithmetic, timestamp comparison, position sizing, fee calculation, or execution. The exact feature definitions, question text, action mapping, JEV model, and thresholds are versioned as one strategy bundle.

## Comparisons

Every run evaluates three methods on the same source snapshot, starting cash, symbols, 10%-per-stock cap, fill assumptions, and fees:

1. JEV `trend_momentum_v1`;
2. deterministic SMA20/SMA60 crossover; and
3. buy-and-hold from the first eligible post-warm-up minute until forced close.

Report net profit, return, maximum intraday drawdown, trade count, total costs, per-stock contribution, and differences between methods.

## Persistence and reproducibility

- Completed runs are immutable; rerunning creates a new run.
- Cache exact Alpaca bars by date, symbol, feed, and source digest.
- Use one SQLite database for transactional run records and offer CSV downloads.
- Record requested and returned pinned JEV model versions, strategy version, question version, fee version, source digest, and execution-model version.
- A failed or invalid JEV call becomes ABSTAIN for only that stock and minute after bounded retries; the run continues.
- API keys remain in server environment variables and never enter browser responses, logs, SQLite, or Git.

## Frontend

One responsive native HTML/CSS/JavaScript page provides:

- historical-date Run form;
- background-job progress;
- immutable completed-run list;
- selected-run comparison summary;
- equity curve;
- per-stock contribution, fills, fees, and positions;
- filterable JEV decision log showing action, probabilities, feature inputs, and deterministic explanation; and
- CSV downloads.

No frontend framework, router, component library, or live brokerage order ticket is needed.

## Recommended TDD seams

Tests should verify behavior only through these public seams:

1. **Historical data seam:** completed date + symbols -> validated immutable market-data snapshot/cache result.
2. **Strategy seam:** minute features + portfolio snapshot + stock -> typed BUY/HOLD/SELL/ABSTAIN decision; use a fake decision provider in simulator tests.
3. **Simulation seam:** immutable run request + market snapshot + decision provider -> completed persisted run and comparison results.
4. **Read-model seam:** completed run ID -> dashboard/CSV data contract.
5. **HTTP seam:** create run, inspect progress, list runs, read result, and download CSV through public endpoints.

Do not test JEV internals, SQLite implementation details, private indicator helpers, or DOM implementation structure directly.
