# Implementation Notes — Phase 0 (Interaction Replay capture)

> Running log of decisions, deviations, and tradeoffs made while implementing
> Phase 0 of the interaction-replay plan, that were NOT pre-specified. Read this
> alongside the commits.

**Scope (Phase 0):** capture the model INPUT faithfully + close the cheap gaps so
that user↔AI trajectories are replayable later.

1. New durable event `model.request_prepared` = the input snapshot.
2. Fix `prompt.submitted.model` (was `''`).
3. Add token `usage` to `message.assistant_completed`.
4. Enrich `tool.render_chart.*` payloads with the `x/y/color` args.

---

## Decisions made (not in the spec)

### D1. Capture the input snapshot in the BACKEND, not the frontend
**Why:** the goal is *replay fidelity* — "what did the model actually receive". The
frontend only knows `extraSystemPrompt`, but the value actually sent is
`effectiveSystem = params?.system ?? $settings?.system ?? extraSystemPrompt`
(Chat.svelte). The single source of truth for "what the model saw" is the backend
`form_data['messages']` (the resolved system message) + `form_data['model']`. So
the snapshot is built from `ctx['form_data']` at the lifecycle hook.

**Tradeoff:** the hook fires at completion time, not request time. That's fine —
`form_data` is unchanged across the turn, and emitting once per completion keeps
the core-touch tiny (no second hook).

### D2. Pass `form_data` + `usage` into the existing lifecycle hook (vs. a new hook)
To avoid a second `[core-touch]` in middleware, `schedule_chat_lifecycle_events`
gains two optional kwargs (`form_data`, `usage`) and does ALL extraction in vertical
code (`event_logger.py`). Middleware change is only "pass two more args" at the two
existing call sites. Non-streaming site reads `ctx['form_data']` /
`response_data.get('usage')`; streaming site already has `form_data` / `usage`.

### D3. Store the FULL resolved system prompt (+ a sha256), not just a hash
The system prompt (incl. the ephemeral `[Workspace context]` block we inject) has no
PII and is ~2KB. For replay you must rehydrate the exact instruction the model saw;
a bare hash needs a prompt registry we don't have until Phase 1. So we store the full
text AND `system_prompt_sha256` (cheap dedup/versioning handle for later).
**Tradeoff:** ~1–2KB per assistant turn in `data_analysis_events`. Acceptable
(charts are ~60KB). Revisit if volume explodes → switch to hash + registry in Phase 1.

### D4. `params` is stored as a curated whitelist, not raw
`metadata['params']` can carry large / irrelevant / potentially sensitive fields
(and a duplicate `system`). We store only replay-relevant keys:
`temperature, top_p, top_k, max_tokens, seed, function_calling, reasoning`.
**Why:** keeps the row small and avoids leaking unexpected fields. `function_calling`
is the important one (native vs default changed behavior dramatically in QA).

### D5. Bump `message.assistant_completed` to `schema_version = 2`
Adding `usage` changes its payload shape. Per the ledger discipline ("schema 變動必須
bump version"), additive or not, the event's schema_version goes 1 → 2. Consumers can
branch on it. `model.request_prepared` ships as schema_version 1 (its first version).

### D6. `prompt.submitted.model` fixed via a 3rd arg on `onPromptSubmit`
`onPromptSubmit(prompt, chatId)` → `onPromptSubmit(prompt, chatId, { model })`. The
model id (`selectedModels[0]`) is only known inside Chat.svelte, so the callback now
forwards it. This is a small change to the already-patched P-003 file.
**Note:** `model.request_prepared.model` (backend) is the *authoritative* record;
`prompt.submitted.model` is now a convenience/cross-check, no longer `''`.

### D7. `model.request_prepared` is backend-emitted → NOT added to the frontend whitelist
`FRONTEND_ALLOWED_EVENT_TYPES` (in routers/data_analysis.py) gates events the browser
may POST. This event is emitted server-side only, so it must NOT be whitelisted (would
let a client forge input snapshots). Left out deliberately.

---

## Live verification (2026-05-26)
One real render confirmed in the ledger:
- `model.request_prepared`: model `MiniMax-M2.7`, `params={function_calling: native}`,
  `tool_ids=[builtin:data-analysis]`, `system_prompt` **contains `[Workspace context]`**
  (ephemeral context now durably captured), sha256 + `message_count` present.
- `message.assistant_completed`: `schema_version=2`, but **`usage: None`**.
- `prompt.submitted.model`: `MiniMax-M2.7` (was `''`).
- `render_chart.succeeded`: `x=timestamp, y=temperature_c, color=None`.

### ⚠️ Known: `usage` came back None
MiniMax's OpenAI-compatible **streaming** response did not include a `usage` object
(many providers omit it unless `stream_options={include_usage: true}` is sent). Our
capture path is correct (schema_v2, populates when present) — the gap is upstream.
Enabling `include_usage` is an upstream/connection-config change, out of Phase 0
scope; logged here so token/cost analytics isn't assumed-working until that's set.

---

# Phase 1 — Trajectory schema + versioning

### D9. Trajectory is rebuilt from the ledger ALONE (no native chat doc)
The ledger already captures request snapshot + every tool call's args + outcome, so
`trajectory.build_trajectory(events)` needs no coupling to `chat.chat.history`. Keeps
it a pure, unit-testable function and avoids a second source of truth.

**Correlation rules (events don't all share a key):**
- Assistant-turn events share `message_id` → grouped into a `Turn`.
- `prompt.submitted` has no `message_id` (fired before the assistant msg exists) →
  paired to the first turn with `ts >= prompt.ts`. Heuristic, but robust for the
  normal one-prompt-one-turn flow.
- `chart.rendered` (frontend, no `message_id`) → attached to the turn whose render
  action produced that `chart_id`.
- `workspace.opened` / `dataset.selected` / `stream.*` → session-level timeline.

### D10. `prompt_version` threads up from frontend; `tool_spec_version` is backend
The system prompt is defined client-side (`system-prompt.ts`), so its version
(`DATA_ANALYSIS_PROMPT_VERSION`) rides in `metadata.data_analysis.prompt_version` and
the backend reads it into the snapshot. `TOOL_SPEC_VERSION` lives in a dependency-free
`utils/data_analysis/versions.py` (so the logger can import it without pulling the tool
registration machinery). Bump each when its contract changes.
**Note:** `system_prompt_sha256` already fingerprints the *resolved* prompt per-turn;
`prompt_version` is the *stable template* version — different granularities, both useful.

---

# Phase 2 — Exporter + replay harness

### D11. Replay re-runs TOOL calls, not the LLM
Re-running the model is non-deterministic and needs a provider. The tool layer is
deterministic against `InMemoryDatasetRepository`, so `replay_trajectory` re-issues
the recorded `query_dataset` SQL + `render_chart` args and diffs success/failure vs.
the recorded outcome. This is the CI-friendly regression signal ("would this
trajectory's tool sequence still work today?"). A recorded *failure* that reproduces
counts as a match (deterministic), so the QA "Unknown column(s): count" case replays
cleanly as fail==fail.

**render_chart caption gap:** title/explanation_* aren't in the ledger, but they don't
affect render success — only x/y/color/chart_type/query_id do (which we have). Replay
supplies placeholder captions. So pass/fail replay is faithful; we just can't
reproduce the human-readable caption text.

**query_id remap:** recorded query_ids are stale; replay maps recorded→freshly-produced
query_id so render actions reference the live cache entry.

### D12. Export honours soft-delete + retention + redaction
`export_trajectories` excludes `is_deleted` chats by default (user-removed = consent
withdrawn), supports a `since_ts` retention window, and a `redact` flag that masks
free-text (`user_prompt`, `system_prompt`) for sharing while keeping structure/metadata.

## Things to know / follow-ups
- Snapshot links to the rest of a turn via `chat_id` + `message_id` (same correlation
  the other lifecycle events use). A full trajectory = request_prepared → tool.* →
  assistant_completed for one `message_id`.
- The ephemeral `[Workspace context]` is now durably captured *as part of the system
  prompt snapshot* — so we get runtime-ephemeral + audit-durable, as designed.
- Not in Phase 0 (deferred to plan Phase 1+): prompt/tool version registry, exporter,
  replay harness, reward signals.
