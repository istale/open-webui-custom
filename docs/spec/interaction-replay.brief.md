# Interaction Replay — Brief / Contract Version

> **Quick reference of `interaction-replay.md`. 修改本檔時必須同步更新 teaching 版。**

Capture user↔AI data-analysis trajectories so they can be replayed for system
enhancement (eval, regression, prompt tuning, failure analysis). Built on the
two-tier ledger; see [`event-ledger.brief.md`](./event-ledger.brief.md).

---

## What gets captured (per assistant turn)

| Signal | Source | Event / field |
|---|---|---|
| **Input snapshot** | backend lifecycle hook (form_data) | `model.request_prepared`: model, curated params, tool_ids, full system_prompt (incl. ephemeral `[Workspace context]`), `system_prompt_sha256`, `prompt_version`, `tool_spec_version`, message_count |
| User prompt | frontend | `prompt.submitted` (now incl. `model`) |
| Thinking | backend | `model.thinking_completed` |
| Tool actions (args) | tool fns | `tool.query_dataset.*` (sql), `tool.render_chart.*` (x/y/color/facet/chart_type/query_id) |
| Outcome + tokens | backend | `message.assistant_completed` (schema_v2, +`usage`) |
| Engagement | frontend | `chart.rendered`, `chart.viewed` (IntersectionObserver ≥50%), `followup.clicked` |
| Reward | OWUI feedback table | thumbs, joined at export by `message_id` |

Correlation: turn = events sharing `message_id`; prompt paired by ts; chart events by `chart_id`.

---

## Version stamps (Phase 1)
- `DATA_ANALYSIS_PROMPT_VERSION` (frontend `system-prompt.ts`) → metadata → snapshot.
- `TOOL_SPEC_VERSION` (`utils/data_analysis/versions.py`) → snapshot.
- Bump on contract change. **Replay only trajectories whose version/schema includes
  what replay needs** (pre-stamp renders lacking x/y are *not replayable*, not failed).

---

## Modules (`backend/open_webui/utils/data_analysis/`)
- `trajectory.py` — `build_trajectory(events)` (pure, ledger-only) → `Trajectory`; `load_trajectory(chat_id)`; `attach_feedback(traj, feedbacks)`.
- `replay.py` — `export_trajectories(since_ts, redact, include_deleted, with_feedback)`; `replay_trajectory(traj, repo)` (deterministic tool re-exec vs recorded outcome).
- `analytics.py` — `summarize_trajectories(...)`, `summarize_replay_reports(...)`.
- `replay_cli.py` — `export` / `regression` (CI gate, non-zero on divergence) / `report`.

```
python -m open_webui.utils.data_analysis.replay_cli report [--since-days N]
python -m open_webui.utils.data_analysis.replay_cli regression
python -m open_webui.utils.data_analysis.replay_cli export --out t.jsonl [--redact]
```

---

## Replay semantics
- Re-executes **tool calls** (deterministic via repository), NOT the LLM.
- Recorded failure that reproduces = **match** (deterministic).
- render_chart captions (title/explanation) not stored → placeholders on replay (don't affect pass/fail).
- query_id remapped recorded→replayed.

---

## Governance (contract)
- **Consent / soft-delete**: `export_trajectories` excludes `is_deleted` by default. Deleting a chat withdraws it from exports.
- **Retention**: `--since-days` / `since_ts` window. No destructive purge (soft-delete only); retention enforced at export.
- **Anonymization**: `redact=True` masks `user_prompt` + `system_prompt`; structure/metadata kept.
- **PII**: prompt_text + thinking_text are raw in the ledger → treat the table as sensitive; redact before sharing externally.

---

## Anti-patterns
- ❌ Rebuild trajectory from native chat doc → use ledger (`build_trajectory`).
- ❌ Persist `[Workspace context]` into messages → ephemeral runtime + durable snapshot.
- ❌ Replay against `http` adapter → use deterministic in-memory repo.
- ❌ Count pre-version-stamp partial trajectories as regressions → not-replayable.
- ❌ Emit `message.thumbs_*` via core touch → join feedback table at export.

---

## 跨檔關聯
- 事件層：[`event-ledger.brief.md`](./event-ledger.brief.md)
- 工具 emit：[`tools-schema.brief.md`](./tools-schema.brief.md)
- 決策日誌：[`../implementation-notes.md`](../implementation-notes.md)（D1–D16）
