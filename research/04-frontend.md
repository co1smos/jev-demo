# Minimal frontend for a paper-trading agent

## Recommendation

Ship one responsive page using semantic HTML, a small CSS file, and one ES module that calls `fetch()`. Use CSS Grid for layout, native tables for dense financial records, `<details>` for optional rationale, `<time>` for timestamps, `Intl.NumberFormat`/`Intl.DateTimeFormat` for locale-aware display, and inline SVG for the equity line [1][2][3][4][5][6][19][20]. This is the smallest viable stack: no framework, router, state library, component kit, or build step.

Use Chart.js only if the equity chart later needs richer interaction such as tooltips or multiple series; its canvas output needs an accessible name and equivalent fallback content [14][15]. Add Preact only when multiple live controls or reusable stateful views make direct DOM updates hard to maintain [17][18].

## Minimum information architecture

One document, in reading order:

1. **Header/status:** agent name, conspicuous “Paper trading” label, market/session state, last successful update, stale/error state, and refresh button.
2. **Portfolio summary:** equity, cash, buying power, day P&L, total P&L, and exposure. Values are the primary content; compact cards are only layout.
3. **Equity:** one line for the selected period, start/end/high/low, and a small data table or text summary as the non-visual equivalent.
4. **Positions:** current holdings and unrealized P&L in a table.
5. **Activity:** newest-first decisions and fills. Each decision exposes its outcome and short reason immediately; full inputs live in `<details>` [3].

Avoid separate pages, navigation, watchlists, candlesticks, order tickets, settings, and live streaming in v1. The page explains what the agent did and the resulting paper portfolio; it is not a trading terminal.

## Content and behavior

### Portfolio/equity summary

- Display money with currency and sign, for example `+$124.20`; do not rely on green/red alone [9]. Use tabular numerals so columns and changing metrics remain aligned [8].
- Day P&L is change since the current trading session opened; total P&L is `equity - initial_equity`. Show both amount and percentage, with the basis stated in the label or tooltip.
- Exposure is gross market value divided by equity. Show `—` for unavailable values, never a fabricated zero.
- Put “Paper trading — no real money” beside the page title, not in a dismissible banner.

### P&L curve

Render a responsive inline `<svg>` with a single polyline/path, visible axes or labeled start/end values, and a zero/baseline where relevant [6]. Keep the chart decorative to assistive technology (`aria-hidden="true"`) and place an adjacent text summary plus compact table of timestamp/equity points behind `<details>`. This avoids treating a picture as the only source of exact values.

Default to the data range returned by the API; offer only native buttons for `1D`, `1W`, `1M`, and `All` if those ranges are actually available. Do not animate the line, and suppress any nonessential motion under `prefers-reduced-motion` [7].

### Positions

Use a real `<table>` with `<caption>Open positions</caption>`, column headers, and one row per symbol [2]:

`Symbol | Side | Qty | Avg price | Mark | Market value | Unrealized P&L | Weight`

Right-align numeric cells. On narrow screens, keep the table semantics and allow horizontal scrolling; do not convert rows into unlabeled cards. An empty state should say “No open positions.”

### Decision rationale and inputs

Each decision row shows time, symbol, action (`buy`, `sell`, `hold`), requested quantity, confidence if the model genuinely produces one, and a one-sentence rationale. A native `<details>` disclosure contains the exact inputs used: prices/features, signal values, risk checks, and rejected constraints [3]. Show values, not a generated narrative reconstruction.

Link a filled decision to its `fill_ids`; link a skipped/rejected decision to explicit checks such as `max_position` or `insufficient_buying_power`. Preserve the agent's emitted rationale verbatim, but treat it as diagnostic data rather than proof that the decision was correct.

### Fills and fees

Show fills newest-first in a table:

`Time | Symbol | Side | Qty | Price | Gross | Fees | Net cash | Decision`

Keep fees separate even when zero. Define `gross = quantity × price`; `net_cash` is signed from the portfolio perspective (negative for buys including fees, positive for sells after fees). If slippage is simulated, expose it as a separate field rather than hiding it in fees.

### Freshness and errors

- Render timestamps with `<time datetime="…">` and visible UTC or exchange-zone text [4]. The API must provide absolute ISO 8601 instants; the browser may format them locally.
- Compare `generated_at` with `freshness.stale_after_seconds`. When stale, keep the last valid data visible, label it “Stale,” and show its age. Never blank the portfolio during refresh.
- Fetch on initial load and manual refresh. A timer may poll at `freshness.poll_after_seconds`; use the Page Visibility API to pause polling while the document is hidden and refresh on return [16].
- `fetch()` does not reject merely because an HTTP error status was returned, so check `response.ok` before parsing [5]. Distinguish transport/API failure from a valid agent error supplied in `errors`.
- Put refresh success/failure in a concise `role="status"` live region so it is announced without moving focus [12]. Keep the persistent error explanation beside the freshness indicator.

## Accessibility baseline

- Use landmarks (`header`, `main`, `section`), one `<h1>`, logical headings, native buttons, tables, details disclosures, and visible keyboard focus [2][3][10].
- Meet at least 4.5:1 contrast for normal text; chart lines, focus rings, and other meaningful non-text graphics need at least 3:1 against adjacent colors [11][13].
- Pair profit/loss color with `+`/`−`, text labels, and line styles or markers; color cannot be the only cue [9].
- Give the refresh control an explicit accessible name, retain focus after refresh, and expose loading with text such as “Refreshing…”.
- Respect reduced-motion preferences and avoid auto-scrolling or flashing updates [7].

## ASCII wireframe

```text
+------------------------------------------------------------------+
| Paper Agent                 [PAPER TRADING]  Market: OPEN         |
| Updated 14:32:08 UTC · 8s ago · Fresh              [Refresh]     |
+------------------------------------------------------------------+
| Equity       Cash        Buying power   Day P&L     Total P&L     |
| $101,240.20  $34,100.00  $68,200.00     +$124.20    +$1,240.20   |
| Exposure 4.3%                                                    |
+------------------------------------------------------------------+
| Equity · 1D                                      +0.12%           |
| $101.3k |                              ____                       |
| $101.0k |____/‾‾\____/‾‾‾‾‾‾‾‾‾‾‾                              |
|          09:30                              16:00                 |
| [Show equity data]                                              |
+------------------------------------------------------------------+
| Open positions                                                  |
| Symbol  Side  Qty  Avg       Mark      Value       UPL    Weight |
| AAPL    Long   20  $218.10   $220.00   $4,400.00  +$38.00  4.3% |
+------------------------------------------------------------------+
| Decisions                                                       |
| 14:31 AAPL  HOLD  Qty 0 — Signal below entry threshold          |
|   [Show inputs and risk checks]                                  |
+------------------------------------------------------------------+
| Fills                                                           |
| 14:02 MSFT BUY 5 @ $430.00  Gross $2,150  Fees $0.20  -$2,150.20|
+------------------------------------------------------------------+
| Status: No agent errors.                                        |
+------------------------------------------------------------------+
```

On small screens, summary cells wrap to two columns and then one; every other section remains in document order, with tables scrolling horizontally.

## Concrete JSON data contract

Serve one `GET /api/dashboard` response. JSON numbers stay numeric; formatting belongs to the client. Money fields use the declared currency and timestamps are ISO 8601 UTC instants. IDs are opaque strings.

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-18T14:32:08Z",
  "agent": {
    "id": "momentum-01",
    "name": "Momentum 01",
    "mode": "paper",
    "state": "running",
    "market_state": "open"
  },
  "freshness": {
    "last_success_at": "2026-09-18T14:32:08Z",
    "stale_after_seconds": 30,
    "poll_after_seconds": 10
  },
  "portfolio": {
    "currency": "USD",
    "initial_equity": 100000.0,
    "equity": 101240.2,
    "cash": 34100.0,
    "buying_power": 68200.0,
    "day_pnl": 124.2,
    "day_pnl_pct": 0.001228,
    "total_pnl": 1240.2,
    "total_pnl_pct": 0.012402,
    "gross_exposure": 4400.0,
    "gross_exposure_pct": 0.043461
  },
  "equity_series": {
    "range": "1d",
    "points": [
      { "at": "2026-09-18T13:30:00Z", "equity": 101116.0 },
      { "at": "2026-09-18T14:32:08Z", "equity": 101240.2 }
    ]
  },
  "positions": [
    {
      "symbol": "AAPL",
      "side": "long",
      "quantity": 20,
      "average_price": 218.1,
      "mark_price": 220.0,
      "market_value": 4400.0,
      "unrealized_pnl": 38.0,
      "unrealized_pnl_pct": 0.008712,
      "portfolio_weight_pct": 0.043461,
      "marked_at": "2026-09-18T14:32:06Z"
    }
  ],
  "decisions": [
    {
      "id": "decision-1842",
      "at": "2026-09-18T14:31:00Z",
      "symbol": "AAPL",
      "action": "hold",
      "requested_quantity": 0,
      "confidence": 0.61,
      "rationale": "Signal remained below the configured entry threshold.",
      "inputs": {
        "last_price": 220.0,
        "fast_ma": 219.42,
        "slow_ma": 219.51,
        "signal": -0.00041
      },
      "risk_checks": [
        { "name": "max_position", "passed": true, "actual": 4400.0, "limit": 10000.0 },
        { "name": "entry_threshold", "passed": false, "actual": -0.00041, "limit": 0.001 }
      ],
      "fill_ids": []
    }
  ],
  "fills": [
    {
      "id": "fill-991",
      "decision_id": "decision-1837",
      "at": "2026-09-18T14:02:11Z",
      "symbol": "MSFT",
      "side": "buy",
      "quantity": 5,
      "price": 430.0,
      "gross": 2150.0,
      "fees": 0.2,
      "slippage": 0.1,
      "net_cash": -2150.2
    }
  ],
  "errors": []
}
```

Contract rules:

- `mode` must be `paper`; the UI refuses to imply live execution for any other value.
- Percentages are decimal ratios (`0.0124` = `1.24%`). Quantities may be fractional.
- Arrays may be empty but are never omitted. Optional unavailable scalar values are `null`, not missing and not zero.
- `errors` entries use `{ "code": "market_data_delayed", "message": "Quotes are delayed", "at": "…", "recoverable": true }`.
- The server computes portfolio, P&L, fees, risk results, and fill linkage. The frontend only formats and presents them; this keeps financial logic deterministic and auditable.

## Sources

1. [MDN: Basic concepts of CSS grid layout](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Grid_layout/Basic_concepts)
2. [MDN: HTML table element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/table)
3. [MDN: HTML details disclosure element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details)
4. [MDN: HTML time element](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/time)
5. [MDN: Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
6. [MDN: SVG in HTML introduction](https://developer.mozilla.org/en-US/docs/Web/SVG/Guides/SVG_in_HTML)
7. [MDN: `prefers-reduced-motion`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion)
8. [MDN: `font-variant-numeric`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/font-variant-numeric)
9. [W3C WAI: WCAG 2.2 Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color)
10. [W3C WAI: WCAG 2.2 Focus Visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html)
11. [W3C WAI: WCAG 2.2 Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
12. [W3C WAI: WCAG 2.2 Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)
13. [W3C WAI: WCAG 2.2 Non-text Contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)
14. [Chart.js: Accessibility](https://www.chartjs.org/docs/latest/general/accessibility.html)
15. [Chart.js: Integration](https://www.chartjs.org/docs/latest/getting-started/integration)
16. [MDN: Page Visibility API](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)
17. [Preact](https://preactjs.com)
18. [Preact: Getting Started](https://preactjs.com/guide/v10/getting-started)
19. [MDN: `Intl.NumberFormat`](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat)
20. [MDN: `Intl.DateTimeFormat`](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat)
