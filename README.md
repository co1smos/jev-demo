# JEV Paper-Trading Simulator

A planned educational simulator for testing whether TypeSafe AI JEV-directed stock decisions would have made money on completed historical US trading days.

The agreed v1 replays one-minute Alpaca data for AAPL, MSFT, and NVDA; persists JEV decisions and simulated fills; and compares JEV with a 20/60 moving-average baseline and buy-and-hold under the same costs and allocation limits.

Status: research and design complete; implementation tickets are tracked in GitHub Issues.

## Documents

- `docs/design.md` — agreed v1 behavior and TDD seams
- `docs/ticket-plan.md` — approved implementation breakdown
- `research/` — cited JEV, strategy, market-simulation, decision-contract, and frontend research
- `AGENTS.md` — visible Herdr worker and model-routing rules

## Safety

This project is educational historical paper trading. It does not place real orders, provide investment advice, or demonstrate future profitability.
