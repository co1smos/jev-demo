# JEV dashboard visualization design

## Goal

Turn the current JEV simulator dashboard from a mostly tabular audit/debug view into a compact visual explanation of:

1. what the stock price was doing,
2. what JEV believed at that moment,
3. which strategy features were changing,
4. when JEV actually changed position, and
5. what happened to portfolio equity afterward.

The dashboard is for understanding historical paper-trading decisions. It should stay simple, native HTML/CSS/JavaScript, and should not become a full trading terminal.

## Design principles

- Prefer a few synchronized time-series charts over many summary widgets.
- Price context is primary. A JEV decision without the corresponding stock price is incomplete.
- Preserve exact audit data, but move verbose/raw data below the visual explanation.
- Use bright, distinct colors for semantic series. Do not render all chart lines in black/gray.
- Keep backgrounds, borders, typography, axes, and non-data chrome neutral so color is reserved for data.
- Avoid gradients, 3D effects, gauge charts, pie charts, decorative shadows, and dense card layouts.
- HOLD is the normal/default state and should not dominate the visual hierarchy.
- BUY/SELL events should be visually obvious.
- All decision-analysis charts for one symbol must share the same time domain and synchronized hover/crosshair behavior.
- Do not add a frontend framework unless the existing native implementation becomes genuinely impractical.

## Information hierarchy

For a selected completed JEV run:

1. Existing method comparison summary.
2. Compact all-symbol decision overview.
3. Per-symbol decision analysis:
   - stock price,
   - JEV probabilities,
   - feature context.
4. Existing method equity curve, enhanced with JEV trade markers where practical.
5. Existing contribution/execution tables.
6. Raw JEV audit table inside a collapsed `<details>` section.

The selected symbol defaults to AAPL and can be switched with simple tabs/buttons:

- AAPL
- MSFT
- NVDA

Do not render three full detailed chart stacks simultaneously on narrow screens.

---

## 1. Decision overview

### Purpose

Answer: **When did JEV actually try to change a position?**

Render one compact row per stock on a shared intraday time axis.

Only show non-HOLD decisions:

- BUY: upward triangle
- SELL: downward triangle
- ABSTAIN/error: small diamond or x

Example:

```text
        10:30       12:00       13:30       15:00
AAPL ----▲-----------▼------▲----------------▼----
MSFT ---------▲--------------------------▼---------
NVDA -----▲---------▼---▲-----------------------▼--
```

Do not show one marker per HOLD minute.

Clicking a marker should:

- select that symbol,
- move/highlight the shared crosshair at that minute,
- expose the exact decision details in the synchronized detail panel.

---

## 2. Stock price chart

### Purpose

Answer:

- What was the stock doing when JEV made the decision?
- At what known price context was the decision made?
- At what later price did the simulated fill occur?

This is the primary chart in the per-symbol analysis section.

### Data source

Use the immutable Alpaca one-minute bars from the exact historical source snapshot used by the simulation.

Do **not** fetch a fresh/current market quote for a historical run.

The dashboard/read model needs to expose the relevant price series from the cached immutable snapshot or persist an equivalent series with the run.

### Price semantics and look-ahead prevention

This is critical.

For a JEV decision at minute `T`, the strategy code uses only bars whose:

```text
bar.timestamp < T
```

Therefore the price shown as the **decision reference price** must be the close of the latest completed bar available before `T`.

Do not label the close of bar `T` as information available to the decision at `T`.

Execution occurs at the next minute's open with the simulation execution model.

A decision/fill sequence should therefore be represented conceptually as:

```text
previous completed bar close -> decision at T -> next-minute open/fill
```

The UI should distinguish:

- Decision reference price
- Decision timestamp
- Execution/fill price and timestamp

### Visualization

First version should use a close/reference-price line rather than dense candlesticks.

Reasons:

- the goal is explaining JEV behavior, not recreating TradingView;
- hundreds of one-minute candlesticks create unnecessary visual noise;
- BUY/SELL markers are easier to read against a line.

Add:

- BUY decision: upward triangle
- SELL decision: downward triangle
- actual fill: smaller circle on the execution timestamp
- forced close: visually distinct but secondary marker

HOLD should not add markers.

---

## 3. JEV probability chart

### Purpose

Answer: **How did JEV's preference change over time, and how decisive was each action?**

Render four probability series on the same 0-1 Y axis:

- BUY
- HOLD
- SELL
- ABSTAIN

The X axis must exactly align with the price chart.

Use normal lines, not a stacked area chart.

### Suggested semantic colors

Use bright colors with sufficient contrast:

- BUY: vivid green, e.g. `#22C55E`
- HOLD: bright blue, e.g. `#3B82F6`
- SELL: vivid red/coral, e.g. `#F43F5E`
- ABSTAIN: purple, e.g. `#A855F7`

These are semantic defaults, not a requirement to use these exact hex values. The important properties are:

- immediately distinguishable,
- bright but not fluorescent,
- readable on a light background,
- reused consistently everywhere.

Do not independently assign random colors per chart.

ABSTAIN may use a thinner or dashed line because it is secondary in normal runs.

Non-HOLD decisions should also get a visible marker on the winning probability series.

---

## 4. Feature context

### Purpose

Answer: **What deterministic inputs changed around the decision?**

Do not put every raw feature on one Y axis.

Use three small synchronized charts beneath the probability chart.

### 4.1 SMA spread

Prefer a derived normalized spread:

```text
(sma20 - sma60) / sma60
```

rather than two near-overlapping absolute price lines.

Benefits:

- centered around zero,
- trend direction is obvious,
- SMA crossover is visible,
- comparable within a stock across the day.

Suggested color: cyan/teal, e.g. `#06B6D4`.

Include a subtle zero reference line.

### 4.2 30-minute momentum

Render `momentum_30` as a zero-centered line.

Suggested color: amber/orange, e.g. `#F59E0B`.

Include a subtle zero reference line.

### 4.3 Relative volume

Render `relative_volume` as small bars or a compact area/bar treatment.

Suggested color: pink/magenta, e.g. `#EC4899`.

Include a subtle reference line at `1.0x`.

### Secondary features

Keep these in the synchronized tooltip/detail panel rather than adding more default charts:

- volatility_20
- trend
- position_state
- position_quantity
- minutes_remaining

---

## 5. Shared hover and detail panel

The price, probability, and feature charts must behave as one coordinated visualization.

Hovering or focusing any chart at minute `T` should show one vertical crosshair across all aligned charts and one compact detail panel.

Example content:

```text
11:42 AM · AAPL

Reference price: $251.20
Decision: BUY

BUY       59%
HOLD      36%
SELL       4%
ABSTAIN    1%

SMA spread: +0.18%
Momentum 30: +0.43%
Relative volume: 1.72x
Volatility 20: ...
Position: FLAT

Execution:
11:43 AM · Buy 39 shares · $251.35
```

If there is no order/fill, omit execution fields rather than showing empty placeholders.

Keyboard focus should expose the same information where practical.

---

## 6. Equity curve

Keep the existing comparison between:

- JEV
- SMA20/SMA60
- buy-and-hold

but improve the visual distinction between series.

Suggested colors:

- JEV: electric blue
- SMA crossover: orange
- buy-and-hold: green

These method colors do not have to match decision-action colors because they represent different semantic categories, but they must remain consistent throughout the page.

Where practical, add small BUY/SELL/fill markers to the JEV equity series. Do not make these markers so large that they obscure the method comparison.

---

## 7. Color system

The UI should feel light, simple, and colorful without becoming busy.

### Neutral UI

Use neutral colors for:

- page background,
- text,
- grid lines,
- axes,
- borders,
- tables,
- cards/sections.

### Color is reserved for data semantics

Recommended palette:

| Meaning | Suggested color |
|---|---|
| BUY | green `#22C55E` |
| HOLD | blue `#3B82F6` |
| SELL | coral/red `#F43F5E` |
| ABSTAIN | purple `#A855F7` |
| SMA spread | cyan `#06B6D4` |
| momentum | amber `#F59E0B` |
| relative volume | pink `#EC4899` |

Avoid relying on color alone:

- BUY and SELL also differ by marker shape/direction.
- Lines should have labels or a compact legend.
- Error/abstain states should have explicit text.

Do not use a rainbow palette for unrelated UI chrome.

---

## 8. Data/read-model changes

The current audit endpoint already exposes:

- minute
- symbol
- action
- four probabilities
- SMA20 / SMA60
- trend
- momentum_30
- volatility_20
- relative_volume
- position state/quantity
- minutes remaining
- linked orders/fills

The missing visualization input is the market price series.

Add a read-model/API representation for the historical bars associated with the selected completed run and source digest.

A reasonable response shape is:

```json
{
  "run_id": "...",
  "symbols": {
    "AAPL": [
      {
        "timestamp": "2026-09-21T14:30:00Z",
        "open": 250.1,
        "high": 250.8,
        "low": 249.9,
        "close": 250.6,
        "volume": 123456
      }
    ]
  }
}
```

The exact endpoint shape is flexible. Prefer extending a coherent selected-run read model over creating many tiny endpoints.

The browser must receive only stored/cached historical data for the run. Loading the dashboard must not call JEV again.

---

## 9. Raw audit table

Keep the exact audit table for debugging and reproducibility, but move it below the visualizations inside a collapsed section:

```html
<details>
  <summary>Show raw decision log</summary>
  ...
</details>
```

Existing audit filters and CSV download should remain available.

The visual charts are an additional read layer, not a replacement for exact audit evidence.

---

# Acceptance criteria

These criteria should be testable through public read-model/HTTP seams where possible. Avoid tests coupled to incidental DOM implementation details.

## A. Data integrity and historical reproducibility

1. Selecting a completed JEV run renders charts entirely from the stored run and its exact immutable historical source snapshot.
2. Loading or interacting with the dashboard does not make another JEV/System One request.
3. Loading a historical run does not fetch a fresh/current stock quote and does not silently substitute newer market data.
4. The price series returned for a run has the same source digest/trading date/symbol universe as the selected simulation.
5. Every rendered decision minute and fill minute maps to the same timestamps stored in the run/audit data.
6. Existing CSV audit export remains byte/data-equivalent in meaning; visualization work must not remove audit fields.

## B. No-look-ahead correctness

7. For a decision at minute `T`, the displayed **decision reference price** is derived only from a completed bar with timestamp strictly earlier than `T`.
8. The UI never presents bar `T` close/high/low as information that JEV knew when making the decision at `T`.
9. If a decision produces an order, the displayed execution price and execution timestamp match the persisted fill generated by the simulator.
10. Decision reference price and fill price are labeled as different concepts.
11. A regression test includes at least one known BUY or SELL and proves the displayed reference bar precedes the decision and the linked fill occurs at the simulator's next-minute execution timestamp.

## C. Decision overview

12. The overview renders exactly one row for each configured symbol in the run.
13. HOLD-only minutes do not produce overview markers.
14. Every BUY decision produces a BUY marker at its exact decision minute.
15. Every SELL decision produces a SELL marker at its exact decision minute.
16. ABSTAIN/error decisions, if present, are visibly distinguishable from BUY and SELL.
17. Selecting a marker selects the matching symbol and exposes the matching minute's details.

## D. Price visualization

18. The selected symbol's price chart contains the historical intraday series for that symbol.
19. BUY and SELL decision markers appear at their exact decision timestamps.
20. Fill markers appear at persisted fill timestamps and use persisted fill prices.
21. Forced-close fills are distinguishable from ordinary JEV-triggered fills.
22. HOLD decisions do not create price-chart markers.
23. Changing the selected symbol updates the price chart without changing the selected run.

## E. Probability visualization

24. BUY, HOLD, SELL, and ABSTAIN probability series are rendered on a common `0..1` scale.
25. For every decision shown, the chart values equal the persisted audit probabilities.
26. The selected action corresponds to a maximum returned probability, consistent with the validated decision contract.
27. The four probability series are visually distinguishable without requiring hover.
28. BUY, HOLD, SELL, and ABSTAIN use the same semantic colors everywhere on the page.
29. The probability chart uses a normal multi-line treatment rather than a stacked area representation.
30. A low-margin decision, where the top two probabilities are close, remains visibly inspectable and is not reduced to only the winning action.

## F. Feature visualization

31. SMA spread is calculated deterministically from stored `sma20` and `sma60` values as `(sma20 - sma60) / sma60`, or an equivalent explicitly documented normalized formula.
32. SMA spread includes a visible zero reference.
33. Momentum uses the stored `momentum_30` values and includes a visible zero reference.
34. Relative volume uses the stored `relative_volume` values and includes a visible `1.0x` reference.
35. Feature charts do not combine incompatible units on one Y axis.
36. Volatility, position state, position quantity, and minutes remaining remain accessible in the minute detail view even if they are not default chart series.

## G. Synchronized time interaction

37. Price, probability, SMA spread, momentum, and relative-volume charts use the same intraday X domain for the selected symbol.
38. Hovering/focusing minute `T` in one chart highlights the same minute `T` in the other synchronized charts.
39. The detail panel shows values for one exact minute, not values independently rounded to different nearest timestamps.
40. Moving the pointer/focus away does not mutate the underlying selected run or audit filters.
41. Clicking a decision marker pins or otherwise exposes that exact decision sufficiently for a user to inspect it without chasing the cursor.

## H. Color and accessibility

42. Data series use a bright, distinct color palette; the completed implementation must not render all major chart series as black/gray.
43. Neutral UI chrome remains visually restrained so chart colors carry semantic meaning.
44. BUY and SELL remain distinguishable by marker shape/direction in addition to color.
45. Every chart series is identifiable through labels, legend, direct labels, or accessible text.
46. Charts retain readable contrast on the dashboard's supported light background.
47. Interactive chart elements that are keyboard reachable expose meaningful text rather than color-only information.
48. Existing visible focus styles remain functional.

## I. Responsive/simple UI

49. The page remains usable at a typical mobile width (~375 CSS px) without horizontal page-level overflow.
50. On narrow screens, detailed analysis shows one selected symbol at a time instead of three full chart stacks.
51. Tables may retain their existing internal horizontal scrolling behavior.
52. Charts resize to their containers without clipping labels or markers materially.
53. The visualization does not introduce a frontend framework, router, or component library unless separately approved.
54. Initial load should not render hundreds of DOM text nodes for HOLD markers; HOLD is represented primarily by probability lines/raw audit data.

## J. Existing functionality must not regress

55. A user can still start a historical run.
56. Background progress/polling still works.
57. Completed-run history still loads and selecting a run still works.
58. Existing method-comparison metrics remain numerically unchanged.
59. Existing equity data remains available.
60. Per-stock contribution, fills, fees, and ending positions remain available.
61. Audit filters for symbol/action/minute still work.
62. CSV download still works.
63. Failed/running run behavior remains unchanged unless explicitly extended by this design.

## K. Error and empty states

64. A completed run with no non-HOLD decisions still renders valid price/probability charts and an empty decision overview without failing.
65. Missing/invalid visualization data produces a clear local error state instead of breaking the whole dashboard.
66. A symbol with no fills still renders its decision analysis correctly.
67. ABSTAIN/error decisions render without requiring an order or fill.
68. The dashboard never fabricates a price, probability, feature, order, or fill to fill a visual gap.

## L. Verification scenario

Automated verification should include at least one completed fixture/run containing:

- all three symbols,
- many HOLD decisions,
- at least one BUY,
- at least one SELL,
- linked order/fill data,
- complete minute bars,
- probability and feature values.

The verification should establish, through public APIs/read models plus a rendered-dashboard smoke test, that:

1. the selected run is the run being rendered;
2. the expected symbols are present;
3. price data is present and correctly time ordered;
4. known BUY/SELL events appear at the expected timestamps;
5. a known decision's four probabilities match stored audit data;
6. the known decision reference price comes from a strictly earlier completed bar;
7. the known linked fill matches stored execution timestamp/price;
8. all synchronized series cover the same selected intraday domain;
9. the raw audit and CSV endpoints remain usable;
10. existing comparison metrics remain unchanged.

## Non-goals

Do not turn this iteration into:

- live trading,
- live quote streaming,
- candlestick/technical-analysis workstation,
- portfolio optimizer,
- JEV explanation generation,
- new trading strategy logic,
- backtest parameter tuning,
- a frontend architecture rewrite.

The goal is a clearer read-only visualization of decisions the simulator already made.
