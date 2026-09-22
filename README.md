# JEV Paper-Trading Simulator

A planned educational simulator for testing whether TypeSafe AI JEV-directed stock decisions would have made money on completed historical US trading days.

The agreed v1 replays one-minute Alpaca data for AAPL, MSFT, and NVDA; persists JEV decisions and simulated fills; and compares JEV with a 20/60 moving-average baseline and buy-and-hold under the same costs and allocation limits.

## Setup and run

Use Python 3.10+ and Node.js 24+. Export the variables shown in `.env.example`:

- `TYPESAFE_API_KEY` calls the pinned JEV model.
- `ALPACA_API_KEY` and `ALPACA_API_SECRET` fetch historical SIP minute bars.
- `JEV_DEMO_DATABASE`, `JEV_DEMO_CACHE`, and `JEV_DEMO_PORT` optionally select local runtime paths and the listening port.

The application reads environment variables directly; it does not load `.env`
files. Start it with:

```sh
npm start
```

Open http://127.0.0.1:8000/. The page reports missing configuration by name
without displaying its value. Choose a completed US trading date, wait for the
background run, then select it to inspect the three methods and download the JEV
decision CSV.

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
