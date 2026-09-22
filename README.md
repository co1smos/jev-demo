# JEV Paper-Trading Simulator

An educational simulator for testing whether TypeSafe AI JEV-directed stock decisions would have made money on completed historical US trading days.

The agreed v1 replays one-minute Alpaca data for AAPL, MSFT, and NVDA; persists JEV decisions and simulated fills; and compares JEV with a 20/60 moving-average baseline and buy-and-hold under the same costs and allocation limits.

## Quickstart

Use Python 3.10+ and Node.js 24+:

```sh
npm ci
cp .env.example .env
chmod 600 .env
```

Fill in these values in `.env`:

- `TYPESAFE_API_KEY` calls the pinned JEV model.
- `ALPACA_API_KEY` and `ALPACA_API_SECRET` fetch historical SIP minute bars.

Do not commit or paste these credentials into logs or chat. `.env` is ignored by
Git. Load it into the process and start the server:

```sh
set -a
. ./.env
set +a
npm start
```

Open http://127.0.0.1:8000/. If the server runs on another machine, keep it bound
to loopback and use an SSH tunnel:

```sh
ssh -L 8000:127.0.0.1:8000 ubuntu@YOUR_SERVER
```

Then open http://127.0.0.1:8000/ on your own computer. Stop the server with
Ctrl-C.

## Run a simulation

1. Open the dashboard and confirm Alpaca and TypeSafe are reported as configured.
2. Choose a completed US trading date. The default is the latest completed
   exchange session.
3. Select **Run simulation**. Processing happens in the background; leave the
   server running while progress updates.
4. When it finishes, select the completed run from the list.

Each simulation uses one shared $100,000 paper portfolio for AAPL, MSFT, and
NVDA. It observes the first 60 completed minutes, then compares these methods
under the same data and cost assumptions:

- pinned JEV `jev-1.13.0` decisions;
- SMA20/SMA60 crossover;
- buy-and-hold.

Starting another simulation creates a distinct immutable run. Repeating a date
reuses its validated market-data cache rather than changing an earlier result.

## Read the dashboard

Selecting a completed run shows:

- net profit, return, maximum drawdown, trade count, and total costs for all
  three methods;
- differences from buy-and-hold and per-stock contribution;
- equity curves plus exact tabular equity values;
- JEV fills, fees, final positions, and realized P&L;
- a minute-by-minute JEV audit trail with input features, probabilities,
  requested/returned model versions, decisions, explanations, orders, and fills.

Filter the audit trail by stock, action, or minute. Select **Download CSV** to
export the currently selected run's audit records.

## Runtime files and options

By default the server writes `jev-demo.db` and `.jev-demo-cache/` in the project
directory. Both are ignored by Git. Optional environment variables are:

- `JEV_DEMO_DATABASE` — SQLite database path;
- `JEV_DEMO_CACHE` — immutable market-snapshot cache directory;
- `JEV_DEMO_PORT` — loopback HTTP port, default `8000`.

Completed runs survive a restart. A run interrupted by a server restart is
marked failed rather than silently resumed; start a new run for that date.

## Reproduce the recorded historical check

With the same credentials exported, run:

```sh
python3 -m jev_demo.verification 2026-09-18
```

The command performs two immutable runs. Its temporary cache starts empty, so
the first run fetches Alpaca and the second proves reuse of the same source
digest. It calls pinned JEV for both runs, renders the dashboard through HTTP,
exports both CSV files, and prints versioned metrics and passing checks without
printing credentials. The captured output is in
[`docs/verification/2026-09-18.json`](docs/verification/2026-09-18.json).

## Limitations

Runs cover AAPL, MSFT, and NVDA regular-session minute bars only. Fills use the
next minute's open with a fixed adverse two-basis-point cost and modeled retail
fees; they do not reproduce spreads, market impact, latency, queue position,
corporate actions, taxes, or live brokerage behavior. Provider errors become an
ABSTAIN after bounded retries.

## Documents

- `docs/design.md` — agreed v1 behavior and TDD seams
- `docs/ticket-plan.md` — approved implementation breakdown
- `research/` — cited JEV, strategy, market-simulation, decision-contract, and frontend research
- `AGENTS.md` — visible Herdr worker and model-routing rules

## Safety

This project is educational historical paper trading. All results are
hypothetical. It does not place real orders, provide investment advice,
demonstrate future profitability, or guarantee that a strategy will perform
similarly in live markets.
