# Project brief for Claude Code

This is a personal fork of Open WebUI with a **data-analysis vertical workspace**
(manufacturing process monitoring). Read this first; every session starts cold.

## What this project is

- Open WebUI's native chat is the centre column, untouched. We added a left
  panel (dataset/filters), a right panel (chart canvas), and four tools
  (`list_datasets`, `query_dataset`, `render_chart`, `summarize_data`).
- A second goal layered on top: every user↔AI turn is **captured for replay**
  so the system can be evaluated, regressed, and improved from real usage.

## Non-negotiable rules

Before touching code, check whether your change interacts with any of these:

1. **Tools own all data access.** Never write pandas / matplotlib / file I/O
   in app code or system prompts. The model must call `query_dataset` /
   `render_chart` — it must not freelance code. See `docs/spec/tools-schema.md`.

2. **Ephemeral runtime vs durable audit.** The `[Workspace context]` block
   (current dataset / filters) is injected fresh every turn via
   `buildDataAnalysisSystemPrompt` in `src/lib/components/data-analysis/system-prompt.ts`
   and **never written to chat history**. The durable copy lives in the
   `model.request_prepared` ledger event. Don't merge them.

3. **`[core-touch]` discipline.** Any edit to an upstream Open WebUI file MUST
   prefix the commit message with `[core-touch]` and add an entry in
   `docs/UPSTREAM_PATCHES.md` (P-001 … P-010 today). This is what makes
   future rebases survivable.

4. **Event schema bump on every contract change.** If you change the payload
   of any `data_analysis_events` event type, bump its `schema_version`. If you
   change the prompt template, bump `DATA_ANALYSIS_PROMPT_VERSION` in
   `system-prompt.ts`. If you change a tool's contract, bump `TOOL_SPEC_VERSION`
   in `backend/open_webui/utils/data_analysis/versions.py`.

5. **Two-tier storage.** Live UI state → chat.metadata (OLTP). Behavioural
   events → `data_analysis_events` ledger (OLAP, soft-delete only). Don't
   collapse them.

## Where things live

- **Spec briefs (read these before touching the matching subsystem)**:
  `docs/spec/*.brief.md` — interaction-replay, llm-eval, fewshot-mining,
  data-analysis-vertical-spec, tools-schema, event-ledger, database-adapter,
  frontend-spec, frontend-design-tokens, PROJECT_GUIDE.
- **Decision log** (every non-spec'd tradeoff): `docs/implementation-notes.md` (D1–D26).
- **Backlog**: `docs/BACKLOG.md`.
- **Vertical backend**: `backend/open_webui/utils/data_analysis/` + `backend/open_webui/tools/data_analysis/`.
- **Vertical frontend**: `src/lib/components/data-analysis/` + `src/routes/(app)/workspace/data-analysis/`.

## The improvement loop (use it, don't reinvent it)

```
capture (Phase 0–1) → trajectory + replay (2) → reward (3)
  → analytics (4) → LLM-eval (5) → few-shot mining (6) → back into prompt
```

CLI is `python -m open_webui.utils.data_analysis.replay_cli` (run from `backend/`):

- `report` — daily health (failure clusters, retry rate, view-through, tokens)
- `regression` — deterministic tool re-execution, non-zero exit on divergence
- `export` — JSONL trajectories for offline use
- `eval` — LLM A/B against a candidate prompt/model/few-shot (needs MINIMAX_*)
- `mine` — produce a version-gated few-shot bank

**Before changing `system-prompt.ts` or any tool contract**: think about
whether `eval` should be run with the candidate to confirm no regression.

## Working environment

- Python venv with all deps: `/Users/istale/Documents/New project/repos/open-webui/.venv`
  (the `xx_dev_env` conda env is missing `aiocache`).
- Run backend: `cd backend && set -a && . ../.env && set +a && PYTHONPATH=. <venv-python> -m uvicorn open_webui.main:app --host 0.0.0.0 --port 8080`
- Run frontend: `npm run dev` (Vite on :5173, not :5174).
- Run tests: `<venv-python> -m pytest tests/data_analysis/ -q` (currently 75 passing).
- `.env` has `MINIMAX_BASE_URL` / `MINIMAX_API_KEY` / `MINIMAX_MODEL`.
- Admin login: `admin@local.dev` / `admin123`.

## Branch / push convention

- Working branch: `vertical/data-analysis`. Don't commit to upstream-tracking branches.
- New commits are NEW commits — never `--amend` and never `--no-verify`.

## Anti-patterns observed in past sessions

- Trying to run things from `/Users/istale/Documents/New project/repos/open-webui` (the **old** sibling repo). Always `cd` to `/Users/istale/Documents/pi-agent-obervation/repos/open-webui-custom`.
- Confusing the venv: tests need the path above; the `xx_dev_env` `pytest` won't import the project.
- Embedding chart URL placeholders (`![](chart-image)`) instead of the real `/api/v1/data-analysis/charts/<id>.png` returned by `render_chart`. The system prompt forbids this; eval scores it.
