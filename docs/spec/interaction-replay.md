# Interaction Replay — Teaching Version

> **修改本檔時必須同步更新 [`interaction-replay.brief.md`](./interaction-replay.brief.md)。**
> Decision log lives in [`../implementation-notes.md`](../implementation-notes.md) (D1–D16).

## 1. Why this exists

Modern agent systems improve by **replaying real user↔AI interactions** — to build
eval sets, catch regressions, tune prompts, and cluster failures. But an LLM only ever
sees `system prompt + messages + tools`; everything in the web app's UI state is
invisible unless we serialize it. So "make interactions replayable" really means:
**durably capture, per turn, the full `input → actions → outcome → reward`**, in a form
you can reconstruct and re-run later.

We already had a behavioral ledger (`data_analysis_events`) and native chat
persistence. What was missing for replay: the *exact model input* (we deliberately
inject the selected-dataset context **ephemerally**, so it wasn't stored anywhere),
model/params/token usage, full tool args, version attribution, reward signals, and the
tooling to export + re-run. This spec fills those gaps in four phases.

## 2. The two halves: ephemeral runtime vs durable audit

A recurring tension (see also the workspace-context design): the model should see
**"now"** (current dataset selection) injected fresh each turn and *not* persisted into
history — otherwise reloading an old chat would feed it a stale selection. But for
*replay* you must know what the model saw. Resolution: keep the runtime message
ephemeral, and write a **durable audit copy** — `model.request_prepared` — at request
time. Same data, two purposes, no contradiction.

## 3. What we capture, per assistant turn

- **`model.request_prepared`** (the input snapshot): model id, curated params
  (`temperature`, `function_calling`, …), `tool_ids`, the **full resolved system
  prompt** including the ephemeral `[Workspace context]`, plus `system_prompt_sha256`,
  `prompt_version`, `tool_spec_version`, `message_count`. Built in the backend from
  `form_data` (the single source of truth for what the model received).
- **`prompt.submitted`** — the user's text (and now the model id).
- **`model.thinking_completed`** — reasoning text + duration.
- **`tool.*`** — every tool call with its args: `query_dataset` (sql), `render_chart`
  (x/y/color/facet/chart_type/query_id). Args are recorded on *failure* too, so a
  failure is analyzable structurally without parsing error strings.
- **`message.assistant_completed`** (schema v2) — duration, tool_call_count, n_chars,
  had_thinking, and `usage` (token counts, when the provider returns them).
- **engagement** — `chart.rendered`, `chart.viewed` (IntersectionObserver, ≥50%
  visible, deduped per chart), `followup.clicked`.
- **reward** — thumbs ratings from Open WebUI's `feedback` table, joined at export.

### Correlation
Assistant-turn events share `message_id` and group into a `Turn`. `prompt.submitted`
has no message_id (it fires before the assistant message exists) so it's paired to the
next turn by timestamp. `chart.rendered` / `chart.viewed` (frontend, no message_id) are
attached to the turn whose render produced that `chart_id`. Session-level events
(`workspace.opened`, `dataset.selected`, `stream.*`) live on a separate timeline.

## 4. Version attribution (why it matters)

Every snapshot carries `prompt_version` (declared in `system-prompt.ts`, threaded via
chat metadata) and `tool_spec_version` (backend `versions.py`). `system_prompt_sha256`
fingerprints the *resolved* per-turn prompt; the version strings name the *stable
templates*. This lets you say "this trajectory ran under prompt v3 / tools v2" and,
crucially, **only replay trajectories whose schema includes what replay needs**. We
learned this the hard way (§7).

## 5. Trajectory model + replay

`trajectory.build_trajectory(events)` is a **pure** function that rebuilds the canonical
`Trajectory` (session events + ordered turns of input/thinking/actions/outcome/charts/
reward) **from the ledger alone** — no coupling to the native chat document, so it's a
single testable source of truth.

`replay.replay_trajectory(traj, repo)` re-executes the **recorded tool calls** (not the
LLM) against a deterministic repository (`InMemoryDatasetRepository`) and diffs each
action's success/failure against what was recorded. Re-running the model would need a
provider and be non-deterministic; the tool layer is reproducible, making this a
CI-friendly regression signal: *"would this trajectory's tool sequence still work
today?"* A recorded failure that reproduces is a **match**. render_chart captions aren't
stored (they don't affect pass/fail), so placeholders are used; recorded query_ids are
remapped to freshly-produced ones.

## 6. Export, analytics, CLI

- `replay.export_trajectories(...)` → JSONL-ready records, honouring soft-delete
  (consent), a `since_ts` retention window, optional PII `redact`, and a `with_feedback`
  overlay.
- `analytics.summarize_trajectories(...)` → failure clustering (by error_code /
  chart_type), self-correction (in-turn retry) rate, chart view-through, token totals.
  `summarize_replay_reports(...)` → a pass/fail regression verdict.
- `replay_cli.py`: `export`, `regression` (exits non-zero on divergence → CI gate),
  `report`. Run from `backend/`:
  ```
  python -m open_webui.utils.data_analysis.replay_cli report
  python -m open_webui.utils.data_analysis.replay_cli regression
  python -m open_webui.utils.data_analysis.replay_cli export --out t.jsonl --redact
  ```

## 7. Lesson: replay fidelity is version-gated

The first live regression run reported 6 "divergences". They weren't regressions — they
were charts created *before* the tool started recording `x/y`, so replay literally
lacked the args. The fix was to classify such actions as **not replayable** (rather than
a false failure), and the broader takeaway is to **filter trajectories by
version/schema before replaying**. This is precisely why §4's version stamps exist.

## 8. Governance

- **Consent**: deleting a chat soft-deletes its events; `export_trajectories` excludes
  `is_deleted` by default, so deletion withdraws data from all exports.
- **Retention**: enforced at export via `--since-days`. We do **not** hard-purge
  (the ledger is soft-delete-only); if a hard purge is ever required it's a deliberate,
  separate, documented operation.
- **Anonymization**: `redact=True` masks free-text (`user_prompt`, `system_prompt`)
  while keeping structure, metadata, and tool args — enough for most eval/regression use
  without exposing user content.
- **Sensitivity**: `prompt_text` and `thinking_text` are stored raw, so the
  `data_analysis_events` table is sensitive; always redact before sharing externally.

## 9. What's next (post-Phase-4)
A live dashboard over `analytics`, LLM-in-the-loop eval (re-run the captured input
against a candidate prompt/model and score), and few-shot / fine-tune candidate mining
from high-reward trajectories. All consume the artifacts defined here.
