# Agent workflow

## Keep delegated work visible

- Run every delegated agent task in Herdr. Do not use hidden native subagents or background delegation for repository work.
- Use one clearly labeled Herdr tab per substantial worker so the user can inspect and interact with it. A brief side-by-side command may use a pane.
- Give each worker a narrow, self-contained brief with its output artifact and exclusions.
- Parallelize independent work, but never let two workers edit the same artifact or checkout concurrently. Use separate worktrees for parallel implementation writers.
- After prompting a worker, verify it entered `working` and install an explicit Herdr waiter. A launch alone is not monitoring.
- Read and verify the worker's artifact or diff before reporting completion. Close only worker tabs created for completed work, and only after the user no longer needs to inspect them.

## Model routing

Use the cheapest capable model; do not spawn an agent just to classify a task.

- Research and design: use a visible Hermes agent directly. A research Hermes agent must do its own research and must not launch Codex, Claude, or hidden subagents.
- Simple mechanical work: handle directly with `gpt-5.6-luna` at medium reasoning.
- Normal research, design, engineering, multi-file changes, business logic, and review: use `gpt-5.6-sol` at medium reasoning.
- Hard debugging, unclear architecture, concurrency, subtle correctness, or a failed Sol attempt: use `gpt-6-astra` at low reasoning.
- Preflight the exact model and effort before launch. Prefer GPT. If the routed GPT model is unavailable, preflight `gemini-pro-agent` and use high reasoning; otherwise use the authenticated agent's verified default and report the fallback.
- Do not escalate merely for confidence. Escalate only when assumptions remain unresolved or verification fails.

## Implementation

- Codex is for implementation only. Do not launch Codex for research, design, planning, or document review.
- Use the official OpenAI Codex CLI as the default implementation worker.
- Work in small vertical slices. For each slice: write a failing test at an agreed public seam, implement only enough to pass, then run the relevant tests, lint, and build.
- Keep implementation workers read-only toward GitHub and shared lifecycle state unless the user explicitly authorizes publication.
- Preserve deterministic control over money, risk limits, validation, idempotency, persistence, and test gates; do not delegate these safeguards to an LLM.
- Review every worker diff and real test output before calling work complete.

## Project design

- Prefer existing open-source or platform features over custom orchestration.
- Keep interfaces small and modules deep; test through public seams rather than internals.
- Record resolved domain vocabulary in `CONTEXT.md` and durable design decisions under `docs/adr/` only when those artifacts become useful.
