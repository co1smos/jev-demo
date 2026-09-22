## Agent skills

### Model routing

Use `gpt-5.6-luna` with high reasoning for every implementation task, including
features, bug fixes, refactoring, tests, code review, and Sandcastle/Codex rounds.

Use `gpt-5.6-sol` with high reasoning for design tasks.

Do not use `gpt-6-astra` for any task until this rule is explicitly changed by
the user. This prohibition applies even to hard, ambiguous, or failed tasks.

Before launching a delegated worker, preflight its exact model and reasoning
effort. If the selected model is unavailable, preflight the configured
`gemini-pro-agent` model ID and use it with high reasoning. If
`gemini-pro-agent` is unavailable or not configured, use the authenticated
Codex account's verified default and report the fallback.

Research and design use visible Hermes agents directly. A research Hermes agent
must perform its own research and must not launch Codex, Claude, or hidden
subagents. Codex is for implementation only.

### Implementation workflow

- Use the official OpenAI Codex CLI as the default coding agent for implementation work in this repository.
- Apply the same model routing to direct Codex work and bounded Sandcastle/Codex iterations.
- When asked to implement a GitHub issue with Codex or Sandcastle—including a concise request such as `Implement issue #5`—load and follow `docs/agents/implementation-workflow.md`. Hermes launches and continuously supervises the deterministic Sandcastle controller through completion; Sandcastle owns the no-sandbox issue worktree and test gates; each Codex phase runs visibly through Unsnooze in a fresh Herdr pane. Hermes must inspect the terminal result and immediately continue with local, reversible correction or finalization; a local-only watchdog is not user notification. The user need not provide shell commands.
- Before Sandcastle preflight, Hermes routes each issue using the model rules above and passes the exact model/effort tuple to the controller. The controller repeats fresh implementer and independent reviewer rounds when the reviewer requests correctable changes. Failed gates, blocked verdicts, and errors remain terminal for that run.
- For implementation, the current Hermes tab is the outer orchestrator. Each dependency-ready issue gets one separate labeled Herdr tab containing its deterministic Sandcastle controller, and every transient Codex implementer/reviewer phase appears as a visible pane inside that issue tab. Do not launch an additional Hermes agent per issue unless the user explicitly asks for nested orchestration.
- Keep every delegated worker visible in its issue tab. Do not use Codex's hidden native subagent spawning for repository work, even though `.codex/agents/*.toml` records the tier definitions.
- The user has authorized separate background Herdr tabs for implementation issues. Keep the current orchestrator tab focused and close issue tabs after their branch has been accepted, rejected, or safely preserved.
- Give each worker one narrow dependency-ready issue and launch it with the model and reasoning values in this section. These routing rules override stale `.codex/agents/*.toml` definitions.
- Maximize safe parallelism from the native GitHub dependency frontier, up to three concurrent issue workers. Run fewer when fewer tickets are unblocked or likely file ownership overlaps. Never expose blocked tickets merely to fill capacity.
- Every parallel issue gets a unique Herdr tab, Sandcastle run, branch, and no-sandbox worktree. Workers must not merge, push, close/comment/edit issues, or mutate shared lifecycle state.
- Work in strict vertical RED → GREEN → REFACTOR cycles at the public seams in `docs/design.md`: write and observe a focused failing test first, implement the smallest passing behavior, then run focused and full checks.
- Preserve deterministic control over money, risk limits, validation, idempotency, persistence, and test gates; do not delegate these safeguards to an LLM.
- Review each worker branch independently, rerun tests from that branch, merge reviewed branches one at a time, push, close the corresponding issue, and recompute the native dependency frontier before dispatching more work.
- Continue autonomously through locally correctable findings and newly unblocked tickets. Stop only for a verified external prerequisite, destructive/irreversible choice, safety boundary, or user-reserved decision.

### Issue tracker

Issues and specs are tracked in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

The repository uses the five default canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain-doc layout. See `docs/agents/domain.md`.

### Project design

- Prefer existing open-source or platform features over custom orchestration.
- Keep interfaces small and modules deep; test through public seams rather than internals.
- Record resolved domain vocabulary in `CONTEXT.md` and durable design decisions under `docs/adr/` only when those artifacts become useful.
