# Implementation workflow

Use this workflow for implementing a ready GitHub issue with Codex.

## Natural-language invocation

When the user asks Hermes to implement GitHub issues with Codex or Sandcastle, Hermes must load this document, compute the native dependency-ready frontier, apply the `AGENTS.md` model-routing rules, run the no-model preflight for each selected issue, and—if it passes—start each reviewed workflow in its own background Herdr tab. The user does not need to type the underlying npm or Herdr commands. Run up to three independent frontier tickets concurrently, but run fewer when only fewer are unblocked or their likely file ownership overlaps.

Recommended prompt:

```text
Implement issue #5 using the repository's Sandcastle + Unsnooze workflow. Apply the AGENTS.md model routing, run preflight first, and stop at a local reviewed candidate branch. Do not push, merge, or mutate the issue.
```

The concise form `Implement issue #5` is also sufficient when Hermes is running from the repository root, because `AGENTS.md` points issue implementation to this document. The explicit form is preferable when the requested stopping point or publication policy matters.

## Ownership

- Hermes resolves and dispatches up to three independent dependency-ready issues, monitors every visible Herdr controller/worker pane, independently verifies each branch, then merges, pushes, closes, and recomputes the frontier one issue at a time.
- Sandcastle is a deterministic Node controller. It creates one `noSandbox()` issue worktree, runs tests, validates receipts, and stops at a reviewed local branch.
- Codex implements or reviews one bounded phase. Implementer and reviewer are separate sessions.
- Unsnooze monitors and resumes Codex quota stops. The runner calls `unsnooze _run codex` explicitly; it does not depend on shell wrappers or a background daemon.
- Herdr provides visible panes. The controller closes only panes it creates.

## Model routing

Hermes applies the `AGENTS.md` routing rule to the resolved issue before preflight, then passes the selected tuple through `SANDCASTLE_MODEL` and `SANDCASTLE_EFFORT`. The runner has no hard-coded model default and fails closed when Hermes has not routed the work.

Each round uses that routed tuple for:

1. one implementer;
2. one fresh reviewer.

When the reviewer requests correctable changes, the controller starts another fresh implementer session, runs the focused gate, and starts another fresh reviewer session. Approval advances to final tests. Failed gates, blocked verdicts, and errors remain terminal.

## Preflight

Run without a model call or repository mutation:

```sh
npm run sandcastle:check
```

The preflight verifies:

- required commands;
- one open, dependency-ready `ready-for-agent` issue (or `--issue N` override);
- exact base SHA and candidate branch;
- model, effort, timeout, and test commands;
- the active Codex provider's credential variable by name and presence only.

It never prints the credential value.

Useful overrides:

```sh
npm run sandcastle:check -- --issue 5
npm run sandcastle:check -- --issue 5 --branch sandcastle/issue-5
```

Environment options:

```text
SANDCASTLE_ISSUE
SANDCASTLE_BASE_SHA             default HEAD
SANDCASTLE_BRANCH               default sandcastle/issue-<number>
SANDCASTLE_MODEL                required; selected by Hermes from AGENTS.md
SANDCASTLE_EFFORT               required; paired with the routed model
SANDCASTLE_FOCUSED_TEST         default python3 -m unittest discover -s tests -v
SANDCASTLE_FINAL_TEST           default python3 -m unittest discover -s tests -v && python3 -m compileall -q .
SANDCASTLE_TIMEOUT_SECONDS      default 18000 (5 hours) per phase
```

## Run

Start each deterministic controller in its own visible background Herdr tab. Every concurrent issue must use a unique controller tab, branch, and no-sandbox worktree:

```sh
npm run sandcastle:reviewed -- --issue 5
```

Hermes triggers it by selecting the model/effort from `AGENTS.md`, creating a labeled background tab, and passing the exact issue/branch tuple to that tab's root pane:

```sh
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$PWD" --label "issue-5-sandcastle" --no-focus
herdr pane run <returned-root-pane-id> "SANDCASTLE_MODEL=gpt-5.6-sol SANDCASTLE_EFFORT=medium SANDCASTLE_BRANCH=sandcastle/issue-5 npm run sandcastle:reviewed -- --issue 5"
```

Parse the tab and root pane IDs from the creation response. The controller is not a Codex session and consumes no model quota while it waits. For parallel frontier work, repeat with unique labels and branch names; never share a worktree or branch.

Hermes must remain the outer orchestrator until every launched controller exits. After each launch, record its issue, controller tab/pane ID, wrapper PID, branch, and artifact directory; monitor each exact PID rather than reusable pane-output sentinels, and inspect every final artifact before reporting or merging. Do not end the turn with only a launch acknowledgement. When the controller exits, immediately report one of:

- `reviewed-local-candidate`: include branch, exact head, review verdict, final test result, and warnings; independently verify and finalize it if acceptance is deterministic and already authorized;
- failure: include the failing phase, preserved branch/head, root cause, and the next corrective action already taken when it is local and reversible;
- quota wait/retry: include the preserved phase and retry state without switching models unless the routing fallback is actually required.

For a raw Herdr pane launch, immediately pair the recorded wrapper PID with a tracked background watcher (`while kill -0 <pid>; do sleep 15; done`) using completion notification. The controller remains visible in Herdr, while the watcher wakes this Hermes conversation when the exact process exits. Then inspect the pane, result artifact, tests, branch, and issue state before reporting. Do not use a reusable pane-output sentinel, and do not use a `deliver: local` cron watchdog as user notification; local cron output is remediation-only and is not injected into this live CLI conversation.

Do not start it through an outer Codex session. The controller launches each model-backed pane itself.

Sequence:

```text
resolve/preflight
create noSandbox issue worktree
fresh Unsnooze-managed Codex implementer
validate exact session ID + rollout + committed HEAD
focused controller-owned tests
fresh Unsnooze-managed Codex reviewer
validate independent session + structured verdict + unchanged HEAD
if changes_requested: fresh implementer correction commit, focused tests, fresh reviewer
repeat correction rounds until approved; blocked/errors stop
final controller-owned tests
stop at local reviewed candidate branch
```

## Fail-closed rules

The workflow stops without advancing when:

- provider credential is absent;
- no ready unblocked issue exists;
- output is missing, malformed, or does not match the expected issue/head;
- exact session identity cannot be corroborated in pane and rollout evidence;
- a phase times out;
- implementer does not commit;
- either test gate fails;
- reviewer is blocked;
- reviewer modifies Git HEAD or leaves tracked changes.

The runner never intentionally uses `codex resume --last`. Real Codex rollout IDs are required for validation. A lingering Unsnooze state after pane cleanup is retained as warning evidence, not treated as success.

## Safety

`noSandbox()` runs with the Ubuntu user's permissions. Use the issue worktree boundary, keep prompts free of secrets, and keep worker instructions read-only with respect to GitHub. Workers must not push, merge, close/comment/edit issues, or mutate shared lifecycle state.

Every run stops at a local reviewed candidate. Hermes independently inspects its branch and `.sandcastle/runs/<run-id>/` artifacts, reruns tests, then merges accepted branches one at a time. After each merge, push main, close that issue, and recompute the native dependency frontier before dispatching newly ready work.
Prompts, schemas, receipts, pane evidence, and test logs live under that ignored artifact directory rather than inside the candidate worktree, so workers cannot accidentally commit controller files.

## Natural quota observation

Synthetic quota pause/resume is verified. A real quota boundary should be observed during normal work rather than manufactured by spending credits. When it happens, verify that Unsnooze binds recovery to the exact Codex session and that the phase still produces valid receipt/head evidence.

`codex exec` is a non-interactive batch command: after exhausting its own provider retries it exits on HTTP 429, so Unsnooze has no live Codex process to resume. Sandcastle therefore preserves the phase/worktree and starts fresh Unsnooze-managed attempts with exponential backoff from 1 second up to a 15-minute cap. All attempts share the five-hour per-phase deadline, which covers the provider's maximum rolling quota window while allowing fast recovery from short limits and avoiding sustained retry storms.
