# TypeSafe AI Jev: primary-source research

Research date: 2026-09-20

## Bottom line

Jev is a hosted, text-input decision model, not a chatbot, trading engine, database, scheduler, or autonomous agent. A caller sends one state plus named, typed questions; Jev returns bounded answers and probability distributions rather than prose. Its three public primitives are Choice, Score, and Noul.[1][2][3]

For a once-per-minute paper-trading loop, Jev is technically fast and inexpensive enough, but it is a poor place for arithmetic, indicators, date/time comparisons, portfolio accounting, order sizing, risk limits, or execution control. Its plausible role is narrower: one optional semantic judgment over already-computed, compact state—for example, classifying a short news/event summary or choosing `buy`, `hold`, or `sell` from explicit criteria—while deterministic code owns all market data, calculations, scheduling, validation, persistence, and simulated orders.[6][8]

Recommendation: do not make Jev the strategy. First build the minute loop without it. If a genuinely semantic signal remains, add one pinned-model Jev call in shadow mode, log the complete decision record locally, and measure it against a no-Jev baseline before permitting it to affect paper orders.

## Scope and evidence standard

The verified sections below use only first-party TypeSafe documentation, TypeSafe's official repositories, its legal documents, and TypeSafe's own evaluation site. Product performance claims are identified as vendor claims where independent reproduction was not performed. No live Jev call was made because no API credential was supplied.

Official SDK source was inspected at the current remote `main` heads during this research:

- Python SDK: commit `2ce5c65f13646cab6e6f782328194c9d85f3300a`, release commit for package version 0.7.0.[12]
- JavaScript SDK: commit `66880ccded6cb642dc1809620c2b108c33730214`, release commit for package version 0.6.0.[16]

## Verified facts

### 1. What Jev is

TypeSafe describes Jev as its flagship and first “System One” model: a model for fast, structured decisions that software consumes directly. It evaluates natural-language state and returns typed answers and probabilities; it does not generate replies, code, or reasoning explanations.[1][2]

The public question/answer primitives are:

| Primitive | Caller defines | Returned value |
|---|---|---|
| Choice | a fixed set of options | selected option, full option probabilities, confidence |
| Score | ordered rubric levels | probability-weighted score, legend, level probabilities, confidence |
| Noul | a yes/no proposition | probability that the answer is yes |

All questions in one request see the same state and are evaluated independently. TypeSafe recommends narrow, atomic questions and composition in ordinary code.[1][3]

“Confidence” on Choice and Score is a statistic derived from the returned probability distribution. Noul exposes the yes probability directly and has no separate confidence field. TypeSafe explicitly says calibration is a group-level property and does not guarantee that an individual answer is correct.[2][7]

TypeSafe's launch post says Jev uses Reinforcement Learning for Calibrated Decisions (RLCD), gives up string generation, and targets structured automation. Its speed, cost, comparative-intelligence, and workflow-evaluation results are TypeSafe's own published claims, not independently verified here.[21][24]

### 2. Intended use cases

TypeSafe's documented architecture is “AI-powered software, not agents”: deterministic code owns workflow and side effects, while Jev handles narrow common-sense judgments over unstructured data.[6]

The first-party examples and guidance support these workload shapes:

- classification and routing among known options;
- yes/no semantic detection;
- scoring against a described ordinal rubric;
- confidence-gated escalation or review;
- combining several independent semantic signals in code;
- selecting or ranking bounded candidates; and
- verification or guardrail judgments around another workflow.[3][6][21]

TypeSafe's own workflow evaluations cover security incident triage, agent-trace review, invoice processing, and customer service. The reference labels are derived from other models and the site says the harness is assumed correct, so these results demonstrate TypeSafe's evaluation method and claimed performance, not independent ground truth.[24]

A Choice accepts at most 255 options. TypeSafe recommends an `other` or `none of the above` option when the supplied set may be incomplete.[22]

### 3. Installation and runtime

Jev itself runs as TypeSafe's hosted service. The direct HTTP entry point is:

`POST https://api.typesafe.ai/v1/systemone`

Requests use bearer authentication and JSON. The top-level body contains `state`, `model`, and a nonempty map of named `questions`. The response returns the resolving model, answers under the same names, and token usage.[4]

Supported state is text represented as a string, JSON object, or array. Jev 1.13 does not accept raw image, audio, or video input; such inputs must be transformed before submission.[5][23]

Official client options are:

- Python: `pip install typesafe-sdk` or `uv add typesafe-sdk`; Python 3.10 or newer; synchronous and asynchronous clients; `TYPESAFE_API_KEY` may supply the credential.[9][10][12]
- JavaScript/TypeScript: `npm install @typesafe-ai/sdk`; Node.js 20 or newer; ESM, CommonJS, and TypeScript declarations; `TYPESAFE_API_KEY` may supply the credential.[11][16]
- Plain HTTP/cURL: no SDK is required.[4][9]

The current documented production model is `jev-1.13.0`. `jev-latest` currently resolves to it, but the alias moves when new stable releases ship. The response reports the versioned model that answered. TypeSafe recommends pinning a version when thresholds have been tuned to that version.[5]

Published service limits for Jev 1.13 are 64k tokens for a whole request, with a separate 32k limit for state plus the longest question; 250,000 tokens/second and 1,200 requests/minute; text input only; and $0.042 per million input tokens with output tokens free. TypeSafe warns that rate limits can change without notice.[5]

TypeSafe's launch post claims roughly 70–500 ms end-to-end response time, while the current building guide says most queries complete in about 100 ms. These are vendor-published figures, not a latency guarantee or a measurement from this environment.[6][21]

### 4. Public interfaces

#### HTTP API

The public evaluation API is one JSON endpoint with three question schemas. Documented failure statuses include 401 for authentication, 422 for validation, 429 for rate limiting, and 529 for overload. TypeSafe tells direct HTTP users to apply exponential backoff for 429 and 529.[4]

`GET /v1/models` lists model names available to the account. Versioned IDs may be accepted even when only aliases appear in that listing.[5]

#### Python SDK

The Python SDK's main public clients are `TypeSafeClient` and `AsyncTypeSafeClient`; typed question classes include `Choice`, `Score`, and `Noul`. `system_one(...)` accepts state, questions, an optional model override, retry/timeout overrides, additional headers/body fields, and optionally a custom Pydantic response model.[10]

At inspected commit `2ce5c65…`, the default retry policy permits two retries after the initial attempt, retries connection/time-out errors and HTTP 408, 429, and 5xx, honors retry headers, uses exponential backoff with jitter, and has a 30-second total retry budget by default.[13]

#### JavaScript/TypeScript SDK

The JavaScript SDK exposes `TypeSafeClient.systemOne(...)`, typed question helpers, per-call timeout/retry/header/cancellation options, and inferred answer types.[11]

At inspected commit `66880ccd…`, defaults are a 10-second timeout per attempt and two retries for connection/time-out errors and HTTP 408, 429, and 5xx, with capped exponential backoff, jitter, and `Retry-After` support. The SDK rejects browser use by default because placing the API key in a browser exposes it; server-side use is the intended default.[17][18]

### 5. Persistence and observability

#### Persistence

No first-party API or SDK evidence found in this research describes Jev as maintaining application sessions, trading state, portfolio state, decision history, or a durable workflow ledger. Each documented request evaluates the supplied state; the caller receives a response. Therefore application persistence is the integrator's responsibility.[4][23]

TypeSafe says customer requests and responses are not used to train Jev. Its docs advertise zero-data-retention only for enterprise customers. The public DPA does not promise default zero retention; it says customer personal data is retained as long as necessary for the processing purpose and legal obligations. Teams sending proprietary or regulated market information should obtain contractual clarity rather than infer zero retention from “not trained on.”[5][19][20]

#### Observability

The response includes the resolved model and input/output token usage.[4] The official SDKs expose request/transport diagnostics:

- Python response objects attach the `x-typesafe-request-id` and raw HTTP response.[15]
- Python info logs include status, elapsed milliseconds, retry count, and request ID; debug wire logs include bodies. Secret headers are redacted, but request and response bodies are not.[10][14]
- JavaScript logs request tags, status, latency, request ID, retries, and—at debug level—headers and bodies; auth headers are redacted.[17]

These facilities are request telemetry, not an application decision ledger. A trading experiment must persist its own timestamped inputs, feature version, question definitions, model version, raw probabilities/confidence, timeout/error outcome, deterministic gate result, intended order, simulated fill, and later outcome.

### 6. Limitations

TypeSafe's current Jev 1.13 limitation page says it can read literally, struggles with numeric precision, does not count reliably, is unreliable for date/time comparisons, loses accuracy with indirection, degrades when state contains irrelevant detail, can be influenced by adversarial content in state, can be confused by contradictory instructions/criteria, and cannot generate text. TypeSafe recommends doing arithmetic, counts, conversions, and time operations in code and minimizing state.[8]

Score is not a reliable way to reconstruct exact numeric magnitude; TypeSafe says its score levels are weak in numerical calibration.[8]

Calibration and confidence do not mean correctness for one decision. Thresholds must be tested on the integrator's own labeled data and should scale with the cost of an error.[2][7]

The service is remotely hosted and subject to network failures, timeouts, overload, changing rate limits, and model-version changes behind aliases.[4][5]

The output schema prevents out-of-schema text, but it does not prevent a validly typed, high-confidence wrong answer. TypeSafe's “can't hallucinate” launch wording is best read as a schema/type claim, not as a factual-correctness guarantee; its own docs say individual answers can be wrong.[2][21]

TypeSafe's own reported benchmarks are vendor-run. This research found no first-party trading-specific validation, no paper-trading benchmark, and no evidence that Jev predicts returns, prices, or market regimes.

## Interpretation: fit for a once-per-minute paper-trading loop

### Fit by concern

| Concern | Interpretation |
|---|---|
| Cadence | Good. One call/minute is far below the published 1,200 requests/minute limit, and claimed sub-second latency leaves ample time inside a 60-second paper loop.[5][21] |
| Cost | Good. At the listed price, 1,000 input tokens per call costs about $0.016/day for a 390-minute US cash session and about $4.13 over 252 sessions; a 24/7 loop costs about $0.060/day and $22.08/year. These are arithmetic projections from the published input-token price, excluding surrounding services.[5] |
| Numeric market features | Poor. Indicators, P&L, exposure, stops, sizing, time windows, and comparisons belong in deterministic code; this is also TypeSafe's explicit guidance.[8] |
| Semantic/event features | Plausible. A compact news, filing, or analyst-text summary can be judged with bounded questions, provided source acquisition and summarization occur elsewhere and the integration is validated on historical examples. |
| Strategy reasoning | Weak fit. A broad “should I trade?” prompt hides many interacting judgments and asks for deliberative reasoning. Jev is designed for atomic snap judgments, not multi-step strategy search.[2][3] |
| Risk and execution | Unsuitable as authority. A remote probabilistic model should not own order sizing, hard limits, position checks, idempotency, or simulated execution. |
| Reproducibility | Manageable only with controls. Pin the versioned model, freeze question definitions, canonicalize state, record every response, and treat timeout/error as `no trade`. An alias can change behavior.[5] |
| Auditability | Partial. Typed outputs, probabilities, model ID, token usage, request ID, and latency are useful, but Jev supplies no explanation and no durable strategy ledger.[2][4][15] |

### Appropriate role

Jev can be an optional semantic feature or bounded policy gate. Examples:

- `event_direction`: Choice among `bullish`, `neutral`, `bearish`, `unclear` for a supplied event summary;
- `thesis_supported`: Noul over a short text thesis and the current evidence;
- `regime_description`: Choice among explicit semantic regimes, only if numeric regime calculation is not already sufficient; or
- `data_quality_concern`: Noul over a human-readable upstream warning/error summary.

The code should then combine that signal with deterministic indicators and hard gates. Jev should never receive raw tick history and be expected to calculate trends, returns, volatility, or thresholds.

### Inappropriate role

Do not use Jev to:

- calculate indicators or compare timestamps;
- infer an exact target price, position size, stop, or probability of profit from Score;
- maintain positions, cash, open orders, or strategy state;
- schedule the loop;
- fetch market data or news;
- place, cancel, or reconcile orders;
- replace deterministic risk checks; or
- generate a trade rationale or post-trade report.

### Key experimental risk

At one decision per minute, latency and API price are not the hard problem. The hard problem is proving incremental predictive value without leakage or overfitting. A plausible semantic decision can still be unprofitable after spread, fees, slippage, and regime change. Jev's confidence must not be treated as calibrated probability of trade profitability unless that relationship is measured on held-out trading data.

## Smallest viable integration

Use zero Jev calls in the control path initially. Build the existing minute loop with deterministic features and a no-trade-safe fallback. Then add this minimum experiment:

1. **Keep one process and one existing scheduler.** Do not introduce an agent framework, workflow engine, database service, or queue solely for Jev.
2. **Compute everything numeric in code.** Produce a compact JSON state containing already-computed/bucketed features, current paper position, and at most one short externally produced event summary.
3. **Make one Jev request per minute at most.** Pin `jev-1.13.0`; batch two or three atomic questions in that request. A minimal set is one Choice for `buy | hold | sell | unclear` plus one Noul for whether the supplied evidence clearly supports acting. Include explicit `hold`/`unclear` outcomes.
4. **Shadow only.** For an initial labeled/backtest period, record the Jev recommendation but do not let it alter paper orders.
5. **Apply deterministic gates.** On API error, timeout, missing answer, low confidence/ambiguous probability, stale data, or a failed hard-risk rule, return `hold`. The remote answer proposes; code disposes.
6. **Persist one append-only local record per minute.** JSON Lines or the application's existing datastore is enough. Store UTC timestamp, symbol, state/features, question schema version, pinned model, request ID, latency, usage, complete answer distributions, deterministic baseline decision, Jev-shadow decision, paper fill/outcome, and error details. Do not enable SDK debug logging in production if state is sensitive, because bodies are logged.[10][14][17]
7. **Promote only after measurement.** Compare the deterministic baseline with and without the Jev feature on held-out periods. Require a predeclared improvement metric, stable behavior by market regime, and acceptable maximum drawdown before allowing the Jev signal to influence paper decisions.

For a Python loop, the official synchronous SDK is the smallest convenient integration if the project already uses Python 3.10+. Plain HTTP is smaller in dependency count but requires correctly implementing validation, retry/backoff, timeouts, and error mapping that the SDK already provides. Use the SDK unless dependency minimization is more important than those built-ins.[4][10][13]

## Decision

**Conditional fit as an experiment; not a fit as the trading engine.**

A once-per-minute paper loop is operationally easy for Jev, and a single bounded semantic call can be integrated cheaply. But the model's documented weaknesses align directly with core trading mechanics: math, numeric precision, temporal comparison, multi-hop reasoning, and sensitivity to distracting state. The smallest defensible architecture is deterministic trading code plus an optional, pinned, shadow-mode Jev semantic feature with a fail-closed `hold` path and complete local logging.

## Sources

[1] https://docs.typesafe.ai/introduction
[2] https://docs.typesafe.ai/concepts/system-one
[3] https://docs.typesafe.ai/primitives
[4] https://docs.typesafe.ai/api
[5] https://docs.typesafe.ai/models
[6] https://docs.typesafe.ai/concepts/how-to-build-with-system-one
[7] https://docs.typesafe.ai/confidence
[8] https://docs.typesafe.ai/model-jaggedness/jev-1.13
[9] https://docs.typesafe.ai/introduction/quickstart
[10] https://docs.typesafe.ai/sdk/python
[11] https://docs.typesafe.ai/sdk/javascript
[12] https://github.com/typesafe-ai/typesafe-sdk-python/blob/2ce5c65f13646cab6e6f782328194c9d85f3300a/pyproject.toml
[13] https://github.com/typesafe-ai/typesafe-sdk-python/blob/2ce5c65f13646cab6e6f782328194c9d85f3300a/src/typesafe_sdk/_core/retry.py
[14] https://github.com/typesafe-ai/typesafe-sdk-python/blob/2ce5c65f13646cab6e6f782328194c9d85f3300a/src/typesafe_sdk/_core/transport.py
[15] https://github.com/typesafe-ai/typesafe-sdk-python/blob/2ce5c65f13646cab6e6f782328194c9d85f3300a/src/typesafe_sdk/_core/schemas/base.py
[16] https://github.com/typesafe-ai/typesafe-sdk-js/blob/66880ccded6cb642dc1809620c2b108c33730214/package.json
[17] https://github.com/typesafe-ai/typesafe-sdk-js/blob/66880ccded6cb642dc1809620c2b108c33730214/src/client.ts
[18] https://github.com/typesafe-ai/typesafe-sdk-js/blob/66880ccded6cb642dc1809620c2b108c33730214/src/retry.ts
[19] https://docs.typesafe.ai/legal
[20] https://typesafe.ai/legal/data-processing
[21] https://typesafe.ai/blog/introducing-system-one-models-and-jev
[22] https://docs.typesafe.ai/primitives/choice
[23] https://docs.typesafe.ai/concepts/state
[24] https://evals.typesafe.ai
