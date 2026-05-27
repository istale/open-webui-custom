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

---

# Phase 3 — Reward / quality signals

### D13. Thumbs rewards via export-time join, NOT a new core-touch event
Open WebUI already stores ratings in its `feedback` table (data.message_id + rating).
Rather than core-touching the rating UI to emit `message.thumbs_*` events, the export
overlays ratings with `attach_feedback(traj, Feedbacks.get_feedbacks_by_chat_id)` —
joined by `message_id`. Keeps `build_trajectory` ledger-pure (D9) while still
surfacing the reward. `with_feedback=True` by default in `export_trajectories`.

### D14. `chart.viewed` is the one genuinely-new signal (vertical-only, no core touch)
Engagement ("did the user actually look at the chart") isn't in any native signal, so
ChartCardCanvas gets an `IntersectionObserver` (>=50% visible) → dispatches `view` →
CanvasFeed → page → `chart.viewed` ledger event. Deduped per chart id in localStorage
(`markChartViewedOnce`), so reloads don't re-count. Added to the frontend whitelist.
`followup.clicked` (already P0) is the other engagement signal.

---

# Phase 4 — Close the loop

### D15. Pure analytics + a CLI, not a live dashboard
`analytics.summarize_trajectories` / `summarize_replay_reports` are pure functions
(testable). `replay_cli.py` exposes `export` / `regression` / `report`. `regression`
exits non-zero when any replayable action diverged → drop-in CI gate. A live dashboard
is left as a consumer of these (out of scope).

### D16. Replayability is version-gated — old trajectories are "not replayable", not "failed"
Live regression first reported 6 "divergences" — but they were charts created BEFORE
Phase 0 added x/y to the ledger, so replay literally lacked the args. Fixed
`replay_trajectory` to classify renders with no recorded x/y as `replay_success=None`
(not-replayable) instead of a false failure. **Takeaway (and the point of Phase 1
version stamps):** only replay trajectories whose `tool_spec_version` / event schema
includes what replay needs. After the fix: live data = 10 replayable, 10 matches, 0
diverged, `passed: true`.

### Live loop verified (2026-05-26 data)
`report` over 6 real chats: 26 tool calls, 4 failures clustered as
`VALUE×2` (the count-column issue), `DATASETNOTFOUND×1` (wrong-name guess),
`QUERY_ID_NOT_FOUND×1` (restart-expiry). `total_tokens: 0` (MiniMax omits usage),
`charts_viewed: 0` (chart.viewed is new — no events yet). This is exactly the
enhancement signal the whole effort was for.

### D17. prompt_version is embedded in the prompt text, not chat metadata
Live check showed `prompt_version: None`: `extraMetadata` is persisted to chat
metadata but is NOT forwarded into the *completion request* metadata the backend hook
reads (only `tool_ids` travels that path). Rather than plumb metadata through the
completion call (more core-touch), the version marker is embedded as a line in the
`[Workspace context]` block — so it rides inside the captured `system_prompt`. The
backend parses `prompt_version:\s*(\S+)` from the system prompt as a fallback. Verified
live: `prompt_version: da-sys-2026-05-27`, `tool_spec_version: da-tools-2026-05-27`,
and `chart.viewed` incrementing.

**Known (already in backlog):** `chart.viewed` / `chart.rendered` fired on the
new-chat index route carry `chat_id=null` (the page handler there has no chat id yet);
chart_id is in the payload so trajectories still attach them correctly.

# Phase 5 — LLM-in-the-loop eval

### D18. The agentic tool-call LOOP, not a single completion
The spec draft said "one live LLM call". That's wrong for tool use: the model can't
emit `render_chart(query_id=…)` until it has seen the `query_dataset` result. So
`run_candidate` runs a **bounded loop** (`MAX_STEPS=6`): call model → execute any tool
calls deterministically against the in-memory repo → feed results back as `role:tool`
messages → repeat until a final message (or cap). Only the model calls are
non-deterministic; tool execution is reproducible.

### D19. `complete` is dependency-injected (testable without a network/key)
`run_candidate(case, repo, *, complete=…)` takes the provider step fn as a parameter;
the default wired in the CLI is `llm_client.complete`. Tests pass a stateful fake that
reads the running `messages` to chain on the live `query_id`/chart url — so the whole
loop + scoring is verified offline. `llm_client.py` is the ONLY vertical module doing
live LLM I/O (aiohttp, OpenAI-compatible, MINIMAX_* env).

### D20. Baseline signals come from the ledger; some checks are candidate-only
Scoring compares candidate vs the recorded turn. The ledger has recorded tool
success/ordering (so `used_tools`/`resolved_dataset`/`render_succeeded`/
`tool_workflow_ok` have a baseline), but NOT the recorded final answer text, so
`embedded_real_url` and `recovered_query_id` have **no baseline** → verdict
`candidate_only` (informational, never a regression). A check regresses only when
baseline=True and candidate=False. `summarize_eval_reports` fails the gate on any
regression OR any errored run.

### D21. render url lives at `result.attachment.url`, not `result.url`
`render_chart` returns the image url nested under `attachment.url` (with a flat-`url`
fallback tolerated). The `embedded_real_url` check reads it from there. (Caught in
verification — first pass looked at a flat `url` and scored `embedded_real_url=None`.)

### D22. CLI `eval` candidate prompt via file, `--prompt-version` is just a label
The system prompt is authored frontend-side (`system-prompt.ts`), so the CLI can't
synthesize "prompt v4" from a version string. `eval` takes `--candidate-prompt-file`
for the actual candidate text (omit → re-use each case's recorded prompt, i.e. a
model/params-only A/B). `--prompt-version`/`--model` are tagged onto the verdict for
provenance. Exits non-zero on regression → A/B gate.

# Phase 6 — Few-shot mining

### D23. `final_answer` is unavailable — the ledger stores n_chars, not answer text
An exemplar would ideally carry `request -> tool sequence -> final answer`, but the
ledger only records `message.assistant_completed.n_chars`, never the assistant prose.
So `final_answer` is `None` in every exemplar. Acceptable: the teaching signal is the
**ideal tool sequence** (exact SQL + chart args), and the final prose is mostly "here
is the chart ![](url)". Documented like the render-caption gap (D11). If answer text
ever matters, it'd need a new capture (out of scope).

### D24. Exemplars teach the CLEAN path — failed attempts dropped
`_ideal_tool_sequence` keeps only `success=True` actions. A turn that failed a render
once then recovered (rule 5) still qualifies (single-recovery is exemplary), but the
exemplar shows only the successful query+render — we don't want to teach the model the
mistake, just the fix. Thrashing (>1 failure) disqualifies the whole turn.

### D25. Selection gates reuse Phase 1–3 signals; no new capture
Mining is a **pure** function over exported trajectory dicts: reward via the Phase 3
feedback overlay (thumbs-down hard-excludes), still-works via optional Phase 2
`replay_reports` (chat must have passed), version-gate via Phase 1 stamps (D16
discipline), then diversity (`per_cluster` per `(chart_type, dataset)`) + content-hash
dedup. No core touch, no DB writes — `mine` just reads the ledger via `export`.

### D26. Closing the loop: `eval --fewshot` injects the bank as a system-prompt suffix
`run_candidate` gained `system_suffix`; `format_fewshot_block` renders the bank to
appendable text. So Phase 6 produces the bank and Phase 5 eval is its acceptance test
(score with-vs-without injection) — exactly the with/without gate the spec describes.
Live injection into `buildDataAnalysisSystemPrompt` is deliberately NOT wired yet
(offline artifact first, per the locked decision).

## Things to know / follow-ups
- Snapshot links to the rest of a turn via `chat_id` + `message_id` (same correlation
  the other lifecycle events use). A full trajectory = request_prepared → tool.* →
  assistant_completed for one `message_id`.
- The ephemeral `[Workspace context]` is now durably captured *as part of the system
  prompt snapshot* — so we get runtime-ephemeral + audit-durable, as designed.
- Not in Phase 0 (deferred to plan Phase 1+): prompt/tool version registry, exporter,
  replay harness, reward signals.
