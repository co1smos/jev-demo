# Beginner Algorithmic Stock Strategies for a One-Minute Paper Simulator

## Scope and recommendation

This is an educational simulator design, not a claim that any strategy will be profitable and not personalized investment advice. One-minute bars are convenient for learning deterministic signals and order simulation, but they omit the order book, queue position, many within-bar price paths, and often the bid/ask quotes. The SEC describes modern equity markets as fragmented, automated, data-intensive, and operationally complex; a minute-bar simulator should therefore be treated as a simplified model rather than a miniature exchange.[1]

Recommended first implementation:

- **Minimal baseline:** long-only 20/60 simple-moving-average crossover on one highly liquid, unleveraged broad-market ETF, regular trading hours only, one position at a time, signals calculated from completed bars, and fills no earlier than the next bar.
- **Benchmark:** buy and hold the same instrument over the same test dates, with the same starting cash and initial transaction-cost model.

The baseline is recommended because it has only one understandable signal, naturally emits buy/sell/hold actions, avoids short-sale and leverage complexity, and is easy to audit for look-ahead errors. Moving-average filters and time-series momentum are closely related forms of trend measurement, although the strongest academic evidence for time-series momentum is at much longer horizons than one minute; short-horizon profitability should not be assumed.[8][9]

## Common simulator contract

All candidate strategies should use the same contract so their results are comparable:

1. Use exchange timestamps in US/Eastern and define a session calendar. Initially process only regular trading hours, 9:30 a.m.–4:00 p.m. ET; extended hours generally have lower liquidity, wider spreads, more uncertain prices, and different order handling.[13]
2. At the close of minute `t`, calculate indicators using bars whose timestamps are no later than `t`.
3. Convert the signal into a target state: `LONG`, `FLAT`, or, only in an advanced mode, `SHORT`.
4. Submit the resulting order for the open of minute `t+1` or later. Never fill an order at the same close that created the signal.
5. Apply spread, slippage, fees, position limits, stops, and available-cash checks before recording the fill.
6. Mark the portfolio to market each bar and retain an event log containing the input window, signal, order, assumed fill, costs, position, cash, and equity.
7. Define one explicit policy for missing bars, trading halts, splits, dividends, session boundaries, and rejected orders. Do not silently forward-fill executable prices.

The action vocabulary should be deterministic:

- `BUY`: current position is flat and the entry condition becomes true.
- `SELL`: current position is long and an exit, stop, target, or time-limit condition becomes true.
- `HOLD`: no state transition is required. `HOLD` means keep the current state, not necessarily keep stock; a flat strategy can hold cash.

Use edge-triggered transitions rather than buying on every bar for which an indicator remains bullish. For example, buy only when a fast average changes from at-or-below the slow average to above it.

## Strategy families

### 1. Moving-average trend following

A simple moving average over `n` completed bars is the mean of their closing prices. A crossover strategy compares a fast and slow average. Academic work shows that moving-average crossovers and time-series momentum are closely connected trend filters.[9]

Beginner rule:

- `BUY` when `SMA(20)` crosses from at-or-below `SMA(60)` to above it.
- `SELL` when `SMA(20)` crosses from at-or-above `SMA(60)` to below it.
- `HOLD` otherwise.

Strengths: minimal state, interpretable, and easy to test. Weaknesses: lag, repeated losses in sideways markets, and high sensitivity to costs if the windows are shortened. The published time-series-momentum evidence documents persistence mainly over one- to twelve-month horizons across liquid futures, not a guaranteed one-minute equity effect.[8] Treat 20/60 minute windows as a teaching configuration, then test neighboring values without selecting the luckiest backtest.

### 2. Price momentum

Momentum asks whether recent return continuation persists without necessarily comparing two averages.

A deterministic long-only rule can use the `L`-bar rate of change:

`ROC_L(t) = close(t) / close(t-L) - 1`

Example rule:

- `BUY` when `ROC_30 > +threshold` and price is above `SMA(60)`.
- `SELL` when `ROC_30 <= 0`, a risk exit fires, or the maximum holding period expires.
- `HOLD` otherwise.

Set the threshold before evaluating the holdout period. A zero threshold is easiest to explain; a nonzero threshold can reduce churn but adds a tunable parameter. Do not cite longer-horizon momentum research as proof of a one-minute edge.[8]

### 3. Mean reversion

Mean reversion bets that a sufficiently unusual short-term move will reverse. A standard educational signal is a rolling z-score:

`z(t) = (close(t) - SMA_N(t)) / rolling_std_N(t)`

Example long-only rule:

- `BUY` when `z < -2`.
- `SELL` when `z >= 0`, the stop fires, or the holding limit expires.
- `HOLD` otherwise.

This is especially important to simulate conservatively. Research on intraday stock returns finds that microstructure effects such as bid/ask bounce can induce short-run negative autocorrelation.[10] A strategy may therefore appear to capture reversal in last-trade bars while merely assuming that it can buy at the bid and sell at the ask; realistic spread and next-bar execution can remove the apparent edge. Avoid adding a short leg initially because stock borrow, unlimited theoretical loss, and short-sale restrictions materially change the exercise.[12]

### 4. Breakout

A breakout enters when price exceeds a range established before the decision. A rolling-channel version is simpler than an opening-range version:

- At bar `t`, calculate `prior_high = max(high[t-N : t-1])`; exclude the current bar.
- `BUY` if `close(t) > prior_high`.
- `SELL` if `close(t)` falls below a shorter prior low, a risk exit fires, or the holding limit expires.
- `HOLD` otherwise.

An opening-range breakout instead fixes the high and low from a predefined opening interval and trades a later break. Published ORB research defines long and short entries at predetermined thresholds above or below the opening price, but its results in crude-oil futures were not robust across subperiods; that is a useful warning against generalizing one market or period to US stocks.[11]

For either variant, calculate the boundary only from earlier bars. A current bar cannot both create a new channel high and be treated as though an order had already rested at that newly known level.

## Sizing and portfolio limits

Start with **fixed fractional notional sizing** because it is easy to audit:

- one long position;
- no leverage;
- no short selling;
- target at most 10% of current portfolio equity in the instrument;
- whole-share quantity `floor(target_notional / assumed_entry_price)`;
- skip the trade when the quantity is zero or cash is insufficient after estimated costs.

A later risk-based mode can size against the stop:

`shares = floor(min(max_position_notional / entry_price, risk_budget / abs(entry_price - stop_price)))`

Reasonable educational defaults are a per-trade risk budget of 0.25% of equity and a 10% notional cap. These are design constraints, not claims of optimality. Keep them configurable and report both gross and net exposure. Do not let a very tight stop produce an enormous position; the notional cap is mandatory.

For multiple stocks, add limits before adding ranking sophistication: maximum number of positions, maximum total gross exposure, maximum exposure per symbol, and a deterministic tie-breaker such as symbol order. The simulator should reject, not partially invent, capital that is unavailable.

## Stop loss, take profit, and time exits

Stops are risk controls, not guarantees. A stop order becomes a market order after its trigger, and the execution price may be materially worse than the stop price in a fast market. A stop-limit controls price but might not execute at all.[2]

A beginner risk overlay can be expressed in units of initial risk `R`:

- set a stop at `entry - 1R`;
- set a take-profit at `entry + 1.5R` or `entry + 2R`;
- choose `R` from a fixed percentage or a completed-bar volatility measure such as a multiple of ATR;
- optionally exit after a fixed number of bars or before the session close.

Use stops and targets as separate experiments as well as together. They alter the distribution of returns but cannot manufacture a predictive signal.

Minute OHLC data creates an important ambiguity: if a bar's high reaches the target and its low reaches the stop, the data does not reveal which happened first. The simulator must not choose the profitable path. Use one of these explicit policies:

1. conservative: assume the stop filled first;
2. unresolved: flag and exclude the trade from headline results;
3. higher-resolution replay: resolve with quote/trade data if available.

For gap-through events, fill a market-style stop at the next available simulated price, not at the unreachable trigger price. Partial fills and queue priority cannot be inferred from ordinary one-minute bars, so the first version should limit itself to small simulated orders in liquid instruments and disclose that simplification.

## Spread, slippage, and execution costs

A market order's execution price is not guaranteed, the last trade need not be the next execution price, and routing plus elapsed time can change the result.[2][3] Every result should therefore be shown after costs.

Preferred model when bid/ask data is available:

- market buy: next executable ask plus adverse slippage;
- market sell: next executable bid minus adverse slippage;
- charge commissions, regulatory fees where applicable, and any modeled market impact.

Fallback when only minute trade OHLC is available:

- use next-bar open as the reference;
- add a clearly labeled fixed adverse cost on buys and subtract it on sells;
- test at least three scenarios, for example low, base, and stressed costs;
- never award price improvement by default.

A practical educational base assumption is a fixed 2 basis points per side, with 5 and 10 basis points per side as sensitivity tests, unless instrument-specific quote data supports a better estimate. These are simulator assumptions, not observed universal spreads. Report turnover because a strategy that trades often is disproportionately vulnerable to small cost errors.

Limit orders need a different model. A bar touching the limit does not prove the order filled: available size, queue position, and price path are unknown. The minimal simulator should either model marketable orders conservatively or label limit fills as optimistic and keep them out of the primary comparison.

## Preventing look-ahead and backtest bias

Look-ahead bias occurs whenever a decision or fill uses information unavailable at that simulated moment. Required safeguards:

- compute a bar-close signal only after that bar is complete;
- fill at the next bar or later;
- use rolling windows ending at the decision bar, never centered windows;
- calculate breakout levels from prior bars only;
- lag daily fundamentals, news, index membership, splits, and other external data to their actual availability time;
- fit scalers, thresholds, and parameters on training data only;
- use chronological train/validation/test or walk-forward evaluation, never random shuffling of time-series bars;
- keep one final holdout untouched until the strategy and costs are frozen;
- record every parameter combination tried, not only the winner.

Backtested performance is hypothetical and does not reflect actual trading.[14] Repeatedly trying windows, thresholds, stops, and symbols until one looks good is backtest overfitting; research on the probability of backtest overfitting specifically warns that ordinary holdout methods can be unreliable for investment simulations.[15] For a beginner project, the best defense is not a complicated statistical correction: keep the hypothesis set small, predeclare the parameter grid, show all trials, and require performance to persist in later untouched data after costs.

Also guard against:

- **survivorship bias:** use the securities that actually existed at each date rather than today's winners;
- **corporate-action errors:** use consistently adjusted data for signals and a coherent cash/dividend treatment for P&L;
- **selection bias:** do not choose the symbol after viewing all results;
- **same-bar path bias:** do not assume the favorable order of high and low;
- **warm-up leakage:** indicators may read earlier bars, but trading starts only after all required history exists;
- **benchmark mismatch:** disclose overnight exposure, cash time, and leverage differences.

## Minimal baseline specification

Implement this before the other strategy families:

- **Instrument:** one liquid, unleveraged broad-market ETF selected before testing.
- **Data:** one-minute regular-session OHLCV; at least 60 completed bars of warm-up.
- **Signal:** `SMA(20)` versus `SMA(60)` on completed closes.
- **Entry:** if flat and fast SMA crosses above slow SMA at bar `t`, buy at the simulated open of `t+1`.
- **Exit:** if long and fast SMA crosses below slow SMA at bar `t`, sell at the simulated open of `t+1`.
- **Otherwise:** hold the existing long or cash state.
- **Sizing:** no leverage; at most 10% of current equity; whole shares; one position.
- **Costs:** adverse per-side cost model, with base and stressed runs.
- **Session:** no new orders outside regular hours. Choose and disclose either overnight holding or a fixed pre-close liquidation rule; do not switch after seeing results.
- **Risk-overlay experiment:** after the signal-only baseline is locked, separately test a stop/target overlay with conservative same-bar handling.

The baseline should be judged on net return, annualized volatility, maximum drawdown, turnover, number of trades, win/loss distribution, exposure, and performance by chronological subperiod—not on win rate alone.

## Benchmark specification

Use **buy and hold of the same instrument**:

- buy once at the first eligible next-bar price after the common warm-up;
- apply the same initial spread/slippage and fee assumptions;
- hold through the common end date;
- include distributions consistently with the strategy data and equity accounting.

Compare ending equity, return, volatility, maximum drawdown, and risk-adjusted return. Also report the active strategy's percentage of time invested. A mostly-cash strategy may have lower drawdown simply because it carries less market exposure. If the baseline is forcibly flat overnight, add an exposure note because buy-and-hold includes overnight returns; do not quietly interpret that mismatch as trading skill.

## Regulatory and product cautions

- Keep the product clearly labeled **educational and hypothetical**. Do not present backtests or paper profits as expected returns; the SEC says backtesting is hypothetical and past performance does not necessarily predict future results.[14]
- Paper trading does not reproduce live fills, liquidity, latency, outages, rejected orders, or emotional and operational risk. The SEC notes that interconnected algorithmic markets can create unexpected operational and systems effects.[1]
- If the product later connects to a brokerage account or sends orders, obtain legal/compliance review. FINRA warns that third-party auto-trading services can cause rapid losses and that registered providers are subject to investor-protection rules.[16]
- Avoid personalized recommendations unless the business has analyzed the broker-dealer, investment-adviser, state-law, and Regulation Best Interest implications. Regulation Best Interest applies when a broker-dealer recommends a securities transaction or investment strategy to a retail customer.[17]
- Margin and frequent-trading requirements are changing. FINRA's new intraday-margin rule became effective June 4, 2026, replacing the former pattern-day-trader framework, but firms may phase implementation through October 20, 2027. A real product must check the customer's broker and then-current rules rather than hard-code one regime.[5] Older FINRA investor pages may still describe the former $25,000 PDT rule during the transition.[4]
- Most broker-dealer securities transactions now settle T+1.[6] Cash accounts remain subject to full-payment and freeriding restrictions; paper buying power should not imply that unsettled proceeds are freely reusable in every real account.[7]
- If short selling is added, model borrow availability and cost, margin, dividends owed, and rejection risk. Regulation SHO includes order marking, locate, close-out, and short-sale price-test requirements; short positions can have theoretically unlimited loss.[12]
- Restrict the first simulator to regular hours. Extended-hours trading can have less liquidity, wider spreads, fragmented prices, and limited order types.[13]
- Regulations and broker house rules change. Display the as-of date of legal content and link users to their broker, FINRA, SEC/Investor.gov, and qualified counsel rather than claiming a disclaimer alone resolves the issue.

## Suggested implementation order

1. Buy-and-hold benchmark and accounting.
2. Minimal 20/60 SMA long/cash baseline with next-bar fills.
3. Cost sensitivity and audit log.
4. Conservative stop/target and time-exit handling.
5. Momentum, mean-reversion, and breakout variants, one at a time.
6. Chronological holdout and walk-forward reports.
7. Only then consider multiple symbols, shorting, limit orders, or broker connectivity.

This order keeps the first deliverable small while preserving the controls most likely to determine whether a paper result is honest.
## Sources

[1] https://www.sec.gov/files/algo_trading_report_2020.pdf — SEC Staff Report on Algorithmic Trading in U.S. Capital Markets
[2] https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-14 — SEC Investor Bulletin: Understanding Order Types
[3] https://www.investor.gov/introduction-investing/investing-basics/how-stock-markets-work/executing-order — SEC Investor.gov: Executing an Order
[4] https://www.finra.org/investors/investing/investment-products/stocks/day-trading — FINRA: Day Trading
[5] https://finra.org/index.php/rules-guidance/notices/26-10 — FINRA Regulatory Notice 26-10
[6] https://www.sec.gov/investment/settlement-cycle-small-entity-compliance-guide-15c6-1-15c6-2-204-2 — SEC: Shortening the Securities Transaction Settlement Cycle
[7] https://www.sec.gov/oiea/investor-alerts-and-bulletins/ib_cashaccounts — SEC Investor Bulletin: Trading in Cash Accounts
[8] https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463 — Time Series Momentum
[9] https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2603731 — Which Trend Is Your Friend?
[10] https://conference.nber.org/confer/2008/mms08/korajczyk.pdf — Intraday Patterns in the Cross-Section of Stock Returns
[11] https://www.sciencedirect.com/science/article/abs/pii/S1544612312000438 — Assessing the Profitability of Intraday Opening Range Breakout Strategies
[12] https://www.sec.gov/investor/pubs/regsho.htm — SEC: Key Points About Regulation SHO
[13] https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-42 — SEC Investor Bulletin: Extended-Hours Trading
[14] https://sec.gov/resources-for-investors/investor-alerts-bulletins/ib_performance — SEC Investor Bulletin: Performance Claims
[15] https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253 — The Probability of Backtest Overfitting
[16] https://finra.org/investors/insights/auto-trading-unregistered-entities — FINRA: Risks of Auto-Trading Services Offered by Unregistered Entities
[17] https://www.finra.org/rules-guidance/key-topics/regulation-best-interest — FINRA: Regulation Best Interest
