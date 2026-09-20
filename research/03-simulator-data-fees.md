# Minimal credible US-equity paper-trading simulator

Research date: 2026-09-20

## Recommendation in one paragraph

Build a long-only, cash-funded simulator for US-listed stocks and ETFs, regular trading hours only. Use Alpaca's 15-minute-delayed consolidated SIP stream for the zero-cost MVP, and run the simulator's clock 15 minutes behind wall time; this is more representative than free real-time IEX-only data, because IEX is one venue while SIP consolidates US exchanges. Offer Alpaca Algo Trader Plus ($99/month) as the direct upgrade to real-time consolidated data. Accept only DAY market and limit orders. Fill market orders against the next simulated minute's observed market, charge the actual modeled bid/ask spread plus a small adverse latency cushion, and fill limits only after a trade-through rather than a mere touch. Keep an append-only cash/position ledger, apply cash dividends and splits, charge current sell-side SEC/FINRA fees, and define each P&L day in `America/New_York` against the previous official close. This is the smallest design that is useful without pretending to reproduce exchange queues or market impact.

## 1. Official one-minute data choices and pricing

### Shortlist

| Source | One-minute / quote access | Coverage and delay | Current personal pricing | MVP assessment |
|---|---|---|---:|---|
| Alpaca Basic | REST and WebSocket trades, quotes, and minute bars; free stream is IEX, and SIP history must be at least 15 minutes old | Real-time IEX; 15-minute-delayed consolidated SIP is documented as a feed; 30 streamed symbols; history since 2016 | $0/month | Best zero-cost choice if the simulator deliberately runs 15 minutes behind using SIP. Do not describe IEX-only results as full-market execution. |
| Alpaca Algo Trader Plus | Same API shape, including SIP trades, NBBO quotes, and minute bars | Real-time all-US-exchange SIP; unlimited streamed symbols; no latest-15-minute restriction | $99/month | Smallest clean upgrade for a real-time simulator. |
| Massive Stocks Starter / Developer | WebSocket minute aggregates and stock market endpoints | 15-minute delayed | $29/month / $79/month | Credible alternative, but costs more than delayed Alpaca for this MVP; tier choice mainly changes included products/history. |
| Massive Stocks Advanced | WebSocket minute aggregates and stock market endpoints | Real-time | $199/month | Full-market alternative, but twice Alpaca's personal real-time price for the needs here. |

Alpaca's official plan table lists Basic at free and Algo Trader Plus at $99/month. Basic provides real-time IEX coverage, 30 WebSocket symbols, history since 2016, and excludes the latest 15 minutes of SIP history; Plus provides all-US-exchange real-time coverage, unlimited symbols, and unrestricted recent history.[1] Alpaca identifies `v2/sip`, `v2/iex`, and `v2/delayed_sip` as stock streams, and emits minute bars just after the minute ends.[3] Its FAQ explains that SIP consolidates exchange trades and quotes while IEX is one exchange; Alpaca's own example shows 12,630 eligible IEX trades versus more than 535,000 SIP trades for the same AAPL day.[2]

Massive's official minute-aggregate page lists Stocks Starter at $29/month and Developer at $79/month with 15-minute-delayed WebSockets, and Stocks Advanced at $199/month with real-time WebSockets. Its minute bars cover pre-market, regular, and after-hours, and a minute with no qualifying trade emits no bar.[4]

IEX Cloud should not be considered: IEX officially retired all IEX Cloud products on August 31, 2024.[16]

### Data recommendation

Use Alpaca Basic's delayed SIP data for MVP development and demos. Every event must retain both:

- `exchange_timestamp`: source event time in UTC;
- `received_timestamp`: when the simulator received it;
- `simulation_time`: equal to exchange time, displayed as 15 minutes behind real time in delayed mode.

Never combine a delayed decision signal with a current quote or current account valuation: that silently introduces look-ahead. In real-time mode, switch the feed entitlement to SIP without changing simulator semantics.

Store minute OHLCV bars for strategy inputs, but also retain the latest bid, ask, bid size, and ask size observed by the simulated order time. Bars alone cannot represent the spread. Missing minutes are not zero-volume flat bars unless the source explicitly emits one; carry a valuation price forward, but mark the bar as absent.

## 2. Calendar, hours, and session boundaries

The exchange calendar, not weekdays alone, determines whether orders may execute. NYSE's core equity session is 9:30 a.m.-4:00 p.m. Eastern Time, with exchange holidays and scheduled 1:00 p.m. early closes.[5] Alpaca's Calendar API returns market dates with their actual open and close times, including early closures.[6]

MVP rules:

1. Load and cache the official calendar for the required date range.
2. Interpret session boundaries in the IANA zone `America/New_York`, not a fixed UTC offset or a fixed `EST` offset. This handles daylight-saving changes.
3. Accept orders outside the session, but queue DAY orders for the next session open; expire their unfilled remainder at that session's close.
4. Execute only during the core session. The close can be 4:00 p.m. or the calendar's early-close time.
5. Store all event timestamps in UTC; use New York time only for session/date classification and presentation.

Explicitly omit pre-market, after-hours, overnight trading, opening/closing auctions, halts, Limit-Up/Limit-Down handling, and unscheduled exchange closures from the first MVP. Extended hours have different liquidity and order constraints; including them without a separate model would add apparent coverage more than credibility.

## 3. Minimal execution model

Alpaca's paper-trading specification is a useful lower-bound reference: orders fill only when marketable, a buy limit becomes marketable at or above the best ask, a sell limit at or below the best bid, and fills use the current NBBO. Alpaca also explicitly says its paper model does not account for market impact, latency slippage, queue position, price improvement, regulatory fees, or dividends, and does not constrain order quantity by displayed NBBO size.[7] Those omissions are exactly why a local simulator needs explicit, inspectable assumptions.

### Supported orders

Support only:

- whole-share long positions;
- DAY market buys and sells;
- DAY limit buys and sells;
- cancel before fill.

Reject short sales, fractional shares, margin, stop orders, trailing stops, bracket/OCO orders, and extended-hours flags. Market orders can slip in real markets; limit orders guarantee a price bound but not execution.[8]

### Event ordering and no look-ahead

An order created from completed minute `M` becomes eligible at the start of minute `M+1`. It must never fill using the open, high, low, close, or quote from minute `M` if the strategy did not have that information when deciding.

Process each minute deterministically in this order:

1. activate previously accepted orders;
2. apply the first eligible quote/trade/bar evidence for the new minute;
3. determine fills;
4. post cash, positions, fees, and realized P&L atomically;
5. publish the completed minute to the strategy;
6. accept new orders for the following minute.

Persist the data event IDs and execution-model version on every fill so a run can be replayed.

### Market-order price

For a buy, start at the observed ask; for a sell, start at the observed bid. If only a minute bar is available, use the next minute's open and apply the configured spread estimate. Then add adverse latency slippage:

- buy: `fill = reference_ask × (1 + latency_bps / 10,000)`;
- sell: `fill = reference_bid × (1 - latency_bps / 10,000)`.

Default `latency_bps` to 1 bp, expose it in run metadata, and round the final fill to the security's valid tick. The spread is already paid by crossing from bid to ask; do not also subtract a generic half-spread unless the reference price is a midpoint or bar price.

### Limit-order price and fill condition

- A marketable buy limit fills at `min(ask, limit)`; a marketable sell limit fills at `max(bid, limit)`.
- A resting buy limit fills only when a later eligible trade prints strictly below the limit, or the later ask is strictly below it.
- A resting sell limit fills only when a later eligible trade prints strictly above the limit, or the later bid is strictly above it.
- A mere touch does not fill. This conservative trade-through rule is a small substitute for the omitted queue-position model.
- Fill the entire quantity only when it does not exceed a configurable participation cap. For the MVP, set the cap to `min(1,000 shares, 1% of that minute's volume)`; if volume is missing, do not fill a resting limit and cap a market order at 100 shares.

This is intentionally conservative but not an order-book simulator. Partial fills may be produced only by the participation cap; do not add random partial fills, because seeded deterministic replay is more valuable than unexplained randomness.

## 4. Spread and slippage

Use observed SIP NBBO quotes whenever available. The spread cost is side-specific:

- buy immediately: cross to ask;
- sell immediately: cross to bid;
- mark portfolio: midpoint while the session is active when both sides are valid; otherwise last eligible trade, then previous official close.

Add only the 1 bp adverse latency cushion described above. Record spread cost and latency slippage as separate fill fields:

- `spread_cost = quantity × abs(fill_reference - midpoint)`;
- `latency_cost = quantity × abs(final_fill - fill_reference)`.

Do not infer sophisticated market impact from one-minute bars. The participation cap prevents the most obvious impossible fills, while the report must label results as unreliable for illiquid names, large orders, and sub-minute strategies. Upgrade only when the project has tick quotes/trades and a demonstrated need for a calibrated volume/volatility impact model.

## 5. Commissions and regulatory fees

Use a versioned fee table with effective dates; rates change and should not be hard-coded into historical runs without an as-of date.

For the current Alpaca-like US-equity retail schedule:

| Cost | Side | Current rate | MVP treatment |
|---|---|---:|---|
| Broker commission | Buy and sell | Usually $0 for self-directed US-listed equity trading; Alpaca's schedule allows exceptions/partner arrangements | Default $0, configurable per share or per order |
| SEC Section 31 transaction fee | Sell only | $20.60 per $1,000,000 of sale value (`0.0000206 × value`) from 2026-04-04 | Charge on sells, by effective date |
| FINRA Trading Activity Fee | Sell only | $0.000195/share, maximum $9.79 per trade from 2026-01-01 | Charge on sells |
| FINRA CAT fee | Buy and sell | Alpaca passes through $0.000003 per executed equivalent NMS-equity share | Charge both sides if matching Alpaca's published retail economics |

The SEC set the FY2026 Section 31 rate to $0 through April 3, 2026 and $20.60 per million dollars beginning April 4, 2026.[9] FINRA's official schedule sets the equity TAF at $0.000195 per sold share with a $9.79 per-trade cap, effective January 1, 2026.[10] Alpaca's current brokerage schedule publishes the same SEC and TAF rates plus a $0.000003/share CAT fee on buys and sells; it aggregates each fee type daily per account and rounds each aggregate upward to the nearest cent.[11]

For reproducibility, calculate raw fees per fill, aggregate by account/trading date/fee type, then apply the configured broker's rounding policy at end of day. Show both gross P&L and net P&L after spread, slippage, commissions, and fees.

## 6. Cash, positions, and settlement

Maintain an append-only double-entry-style activity ledger rather than mutating only a current balance. Minimum activity types are deposit, withdrawal, buy fill, sell fill, commission, regulatory fee, cash dividend, split, and correction.

MVP account invariants:

- USD only;
- long-only and cash-funded;
- reject a buy unless available cash covers worst-case notional plus estimated fees;
- reserve cash for open buy orders and reserve shares for open sell orders;
- on a buy fill, debit cash and increase quantity/cost basis atomically;
- on a sell fill, credit cash net of fees, reduce quantity, and realize FIFO P&L;
- `equity = cash + Σ(position quantity × mark price)`;
- deposits and withdrawals alter equity but are excluded from trading P&L.

US equities generally moved to T+1 settlement on May 28, 2024.[12] The MVP should record `trade_date` and calculated `settlement_date` (next valid business/settlement day) for auditability, but it should not enforce cash-account freeriding, good-faith violations, margin buying power, or broker-specific withdrawal availability. Filled-sale proceeds may be reused immediately inside this synthetic paper account; label that behavior explicitly rather than claiming it models a regulated cash account.

## 7. Corporate actions

Implement only forward/reverse splits and ordinary cash dividends. Alpaca's official corporate-actions data includes declaration, ex, record, and payable dates, cash per share, and old/new split rates; it states that balances are expected to change on the payable date.[13]

### Splits

Before the affected session opens on the effective/payable date:

- multiply share quantity by `new_rate / old_rate`;
- divide per-share cost basis by the same ratio;
- preserve total cost basis and market value apart from rounding;
- cancel open orders for the symbol rather than attempting to adjust them;
- for a reverse split fractional remainder, create a pending cash-in-lieu item, but allow an operator-supplied amount because the final cash price may not be known immediately.

### Cash dividends

Snapshot the entitled settled quantity using the announcement's record/ex-date fields, then credit `cash_per_share × entitled_quantity` on the payable date. Treat dividends as investment income in total P&L, not as external cash flows. Store corrections as reversing and replacement ledger entries; never overwrite history.

Explicitly omit stock dividends, mergers, spin-offs, rights, tender offers, symbol/CUSIP changes, ADR fees, return of capital, tax withholding, and voluntary elections. Either reject/flag a run that crosses such an event or require a manual adjustment. Silent omission would corrupt positions and P&L.

## 8. Daily P&L and timezone semantics

Define a trading day by the official exchange calendar date in `America/New_York`. Store timestamps in UTC, but assign each event to its New York trading date. Alpaca similarly normalizes portfolio-history boundaries to `America/New_York`, resets intraday equity P&L to the previous trading day's closing equity by default, and returns daily points only for market-open days.[14]

For trading date `D`:

- `start_equity(D)` = equity at the prior trading session's official close after prior-day fees and corporate-action postings;
- `net_external_flow(D)` = deposits minus withdrawals after that close and through the current mark;
- `daily_pnl(t)` = `equity(t) - start_equity(D) - net_external_flow(D)`;
- `daily_return(t)` = `daily_pnl(t) / start_equity(D)` when the denominator is positive;
- realized P&L comes from FIFO closed lots;
- unrealized P&L is current marked value minus remaining lot cost;
- total daily P&L must reconcile to realized plus unrealized plus dividend income minus commissions/regulatory fees, allowing for rounding.

During the regular session, mark long positions at NBBO midpoint when valid, otherwise the last eligible trade. At session close, use the official closing price when available. Freeze that close as the next trading day's baseline, including on early-close days. Alpaca's position documentation likewise uses live/extended-hours last trades during active periods and the primary exchange's official close overnight.[15]

Do not reset at UTC midnight, server-local midnight, or a fixed 5:00 p.m. offset. DST and early closes make those rules wrong.

## 9. Smallest credible MVP boundary

### Build now

1. Alpaca adapter for delayed SIP quotes/trades/minute bars; configuration switch for paid real-time SIP.
2. Official calendar adapter and New York session clock.
3. Whole-share, long-only DAY market and limit orders.
4. Deterministic next-minute execution, observed spread, 1 bp adverse latency, conservative trade-through limits, and participation caps.
5. Append-only USD cash, FIFO lots, positions, reservations, and effective-dated fees.
6. Splits and ordinary cash dividends.
7. Intraday and daily gross/net P&L with prior-official-close baseline.
8. Replay artifact containing source timestamps, input events, model/fee versions, orders, fills, ledger entries, and invariant checks.

### Explicit omissions

- Real brokerage connectivity or custody.
- Shorts, borrow availability/fees, margin, leverage, and interest.
- Fractional shares and options.
- Extended/overnight sessions and auctions.
- Stop, trailing, bracket, OCO, IOC, FOK, GTC, and notional orders.
- Full depth, exchange routing, queue priority, price improvement, maker/taker rebates, and information leakage.
- Calibrated nonlinear market impact; the simulator is not credible for HFT or large participation rates.
- Halts, LULD, busts/corrections, and tick-level race conditions in v1.
- Cash-account settlement restrictions, tax lots other than FIFO, wash sales, taxes, and withdrawals of unsettled funds.
- Complex or voluntary corporate actions and automatic cash-in-lieu pricing.
- Benchmarks claiming live profitability from delayed data.

### Upgrade triggers

Add complexity only when evidence requires it: real-time SIP when wall-clock decisions matter; tick trades/quotes and queue/impact modeling when strategies operate below one minute; extended-hours logic when users actually trade those sessions; and a full corporate-action processor when the supported universe can no longer safely exclude affected symbols.

## Sources

[1] https://docs.alpaca.markets/us/docs/about-market-data-api — Alpaca About Market Data API
[2] https://docs.alpaca.markets/us/docs/market-data-faq — Alpaca Market Data FAQ
[3] https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data — Alpaca Real-time Stock Data
[4] https://massive.com/docs/websocket/stocks/aggregates-per-minute?assetClass=stocks&display=all&license=personal — Massive Per-Minute Stock Aggregates
[5] https://www.nyse.com/markets/hours-calendars — NYSE Holidays and Trading Hours
[6] https://docs.alpaca.markets/docs/calendar — Alpaca US Market Calendar
[7] https://docs.alpaca.markets/us/docs/paper-trading — Alpaca Paper Trading
[8] https://docs.alpaca.markets/us/docs/orders-at-alpaca — Alpaca Orders
[9] https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2 — SEC FY2026 Section 31 Fee Rate Advisory
[10] https://www.finra.org/rules-guidance/rulebooks/corporate-organization/section-1-member-regulatory-fees — FINRA Member Regulatory Fees
[11] https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf — Alpaca Brokerage Fee Schedule
[12] https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq — SEC T+1 FAQ
[13] https://docs.alpaca.markets/reference/corporate-actions-ca-announcements — Alpaca Corporate Actions Announcements
[14] https://docs.alpaca.markets/us/reference/getaccountportfoliohistory-1 — Alpaca Account Portfolio History
[15] https://docs.alpaca.markets/us/docs/working-with-positions — Alpaca Working with Positions
[16] https://iexcloud.io/product-bulletin — IEX Cloud Product Bulletin
