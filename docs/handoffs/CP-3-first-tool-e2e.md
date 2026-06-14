# CP-3 Handoff — First Tool E2E

**Date**: 2026-05-11  
**Tag target**: `first-tool-e2e`  
**Branch**: `vertical/data-analysis`  
**Branch HEAD at handoff creation**: `CP-3 handoff commit`  
**Previous checkpoint**: `adapter-done`

## ✅ Done

- Added `backend/open_webui/tools/data_analysis/tool_module.py`.
  - Exposes native Open WebUI `class Tools`.
  - Implements `list_datasets(tags: str = "", __user__: dict | None = None)`.
  - Calls `get_repository().list_datasets(user_id=__user__["id"], tags=...)`.
  - Returns a schema-versioned JSON-ready payload: `{"schema_version": 1, "items": [...]}`.
- Added `backend/open_webui/tools/data_analysis/__init__.py`.
  - Defines `BUILTIN_TOOL_ID = "builtin:data-analysis"`.
  - Seeds the tool into the Open WebUI Tool DB via `ToolForm` / `ToolsModel`.
  - Uses native `get_tool_specs(instance)` instead of hand-written JSON schema.
  - Grants public read access (`user:* read`) so normal users can resolve the built-in tool.
  - Warms both `app.state.TOOLS[tool_id]` and `app.state.TOOL_CONTENTS[tool_id]`.
- Added the approved P-001 `[core-touch]` in `backend/open_webui/main.py`.
  - Current upstream uses `FastAPI(lifespan=lifespan)`, so the hook is a 2-line call inside the existing lifespan startup path before `startup_complete = True`.
  - `docs/UPSTREAM_PATCHES.md` records commit `a608bb6d6`.
- Fixed an import hygiene issue discovered during CP-3 verification.
  - `repository.py` no longer imports pandas at module import time just to annotate `QueryResult.df`.
  - This keeps tool registration from touching pandas / pyarrow before any query executes.
- Added `tests/data_analysis/test_tool_registration.py`.
  - Covers `list_datasets` payload shape.
  - Covers DB seed + `TOOLS` / `TOOL_CONTENTS` double cache warm.
  - Covers native `function_call_output` text shape expected by Open WebUI output persistence.
- ET-1 handled before implementation.
  - `tools-schema.md`, `tools-schema.brief.md`, `PROJECT_GUIDE.md`, and `UPSTREAM_PATCHES.md` were corrected from `@app.on_event("startup")` to the actual lifespan integration point.

## 📊 Diff Summary

Commits since `adapter-done`:

```text
707f1e32b fix: keep repository pandas import type-only
a6d2fccbd docs: record P-001 core touch commit
a608bb6d6 [core-touch] feat: register data analysis list_datasets tool
dbde1d3e9 spec: align tool registration hook with lifespan startup
```

Diff stat:

```text
backend/open_webui/main.py                         |   4 +
backend/open_webui/tools/data_analysis/__init__.py |  72 ++++++++++
backend/open_webui/tools/data_analysis/tool_module.py  |  64 +++++++++
backend/open_webui/utils/data_analysis/repository.py   |   7 +-
docs/UPSTREAM_PATCHES.md                           |  18 +--
docs/spec/PROJECT_GUIDE.md                         |   2 +-
docs/spec/tools-schema.brief.md                    |  13 +-
docs/spec/tools-schema.md                          |  19 ++-
tests/data_analysis/test_tool_registration.py      | 152 +++++++++++++++++++++
9 files changed, 325 insertions(+), 26 deletions(-)
```

Tier 3 count: still `13/15`. CP-3 used planned files; no new unplanned vertical files were added.

## 🧪 Trace Evidence

Backend-level trace from a `list_datasets` tool call to native Open WebUI output item shape:

```json
[
  {
    "type": "function_call",
    "call_id": "call_list_datasets",
    "name": "list_datasets",
    "arguments": "{\"tags\": \"production,line-a\"}",
    "status": "completed"
  },
  {
    "type": "function_call_output",
    "call_id": "call_list_datasets",
    "output": [
      {
        "type": "input_text",
        "text": "{\"schema_version\": 1, \"items\": [{\"id\": \"sensor_readings\", \"name\": \"Sensor Readings\", \"description\": \"Line A machine sensor readings.\", \"row_count\": 1000000, \"column_count\": 1, \"columns\": [{\"name\": \"timestamp\", \"dtype\": \"datetime64[ns]\", \"nullable\": false, \"unit\": null, \"semantic\": \"timestamp\"}], \"updated_at\": \"2026-05-11T00:00:00+00:00\", \"tags\": [\"production\", \"line-a\"]}]}"
      }
    ],
    "status": "completed"
  }
]
```

Cache double-write verification is covered by `test_register_builtin_data_analysis_tool_seeds_db_and_warms_both_caches`:

```python
assert BUILTIN_TOOL_ID in app.state.TOOLS
assert "def list_datasets" in app.state.TOOL_CONTENTS[BUILTIN_TOOL_ID]
```

## ❓ Open Questions

- Q1: CP-1 deferred P-004 (chart placeholder render path) to CP-3 review. CP-3 only returns text JSON from `list_datasets`; there is still no chart attachment yet. Recommendation: keep P-004 deferred until CP-4 produces the first `render_chart` output, because that is the first checkpoint with real image/native attachment evidence.

## ⚠️ Risk Flags

- R1: Full browser/LLM Native Chat verification was not completed in this local environment. The focused unit/integration tests validate the tool method, DB seed path, cache warming, and native output item shape, but a live `/chat/completions` call needs a fully installed Open WebUI backend environment plus a configured model/auth token.
- R2: A direct import check of `open_webui.utils.tools.get_tool_specs` exposed missing repo-declared local packages in the active Python env (`redis`, then `authlib` after installing DB drivers). I stopped dependency chasing to avoid turning CP-3 into full environment bootstrap. The implementation still calls the native `get_tool_specs(instance)` path in production code.
- R3: The existing pyarrow / NumPy 2.x warning from CP-2 is still relevant for production query/Arrow work. CP-3 reduced startup exposure by making `repository.py` avoid pandas at import time, but adapters still require a compatible data stack when real queries run.

## 🔍 Verify Steps

```bash
cd /Users/istale/Documents/open-webui-based-project

pytest tests/data_analysis/ -v
```

Latest output:

```text
31 passed in 0.35s
```

```bash
grep -rn "import httpx" backend/open_webui/tools backend/open_webui/routers
```

Latest output: no matches.

```bash
python -m compileall -q backend/open_webui/tools/data_analysis backend/open_webui/utils/data_analysis tests/data_analysis
git diff --check
```

Latest output: no errors.

## Decision Awaited

Pick one:

- ✅ APPROVED → proceed to CP-4 (All P0 Tools)
- ✏️ REVISE → specific feedback
- 🔀 PIVOT → re-direction

**Next phase brief if approved**: CP-4 implements the remaining P0 tool methods (`get_dataset_schema`, `query_dataset`, `render_chart`, summary helper), chart renderer coverage for all 9 chart types, server-side image endpoint, and the first real chart attachment path.
