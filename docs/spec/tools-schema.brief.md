# Tools Schema — Brief / Contract Version

> **Quick reference of `tools-schema.md`. 修改本檔時必須同步更新 teaching 版。**

---

## Mechanism (confirmed in codebase)

Open WebUI tool system：
- DB-stored Python source (`tool` table, `content` field)
- `class Tools` convention，每個 method = callable function
- Specs auto-generated via `get_tool_specs(module)` from type hints + docstrings
- `app.state.TOOLS` runtime cache（`main.py:973` 初始化空 dict）
- 觸發方式：`form_data['tool_ids']` 或 `form_data['tools']`（payload）
- 自動注入參數（不出現在 LLM spec）：`__user__`、`__id__`、`__metadata__`、`__messages__`

**`register_tool(schema, handler)` API 不存在** — 用 DB seed + cache warm。

---

## Vertical Tools (5 個)

| Tool | Method | 用途 |
|---|---|---|
| `list_datasets` | `Tools.list_datasets` | 列出可存取 datasets |
| `query_dataset` | `Tools.query_dataset` | SELECT query → query_id + preview |
| `render_chart` | `Tools.render_chart` | 從 query_id 渲染 matplotlib PNG → image attachment |
| `summarize_data` | `Tools.summarize_data` | 文字摘要 |
| `get_dataset_schema` | `Tools.get_dataset_schema` | 拿 dataset 欄位 metadata |

---

## Class Tools 簽名

```python
class Tools:
    def __init__(self):
        from open_webui.utils.data_analysis import get_repository
        from open_webui.utils.data_analysis.query_cache import get_query_cache
        self.repo = get_repository()
        self.query_cache = get_query_cache()

    def list_datasets(self, tags: str = "", __user__: dict = None) -> dict: ...

    def query_dataset(
        self, dataset_id: str, query: str, max_rows: int = 100,
        __user__: dict = None,
    ) -> dict: ...

    def render_chart(
        self,
        query_id: str,
        chart_type: str,           # line/bar/scatter/heatmap/control/spc/histogram/pareto/box
        x: str,
        y: str,
        title: str,
        explanation_source: str,
        explanation_method: str,
        explanation_fields: str,   # comma-separated
        facet: str = "",
        color: str = "",
        explanation_aggregation: str = "",
        explanation_notes: str = "",
        __user__: dict = None,
        __id__: str = None,
    ) -> dict: ...

    def summarize_data(
        self, query_id: str, title: str, summary: str,
        key_findings: str = "",
        __user__: dict = None,
    ) -> dict: ...

    def get_dataset_schema(self, dataset_id: str, __user__: dict = None) -> dict: ...
```

**Flat parameter names** (no nested dict)：跨 LLM 提供商最穩定。

---

## Layer Discipline

| Layer | Where |
|---|---|
| Layer 1: LLM output subset | OpenAI function `parameters` schema (auto-derived from method signature) |
| Layer 2: Backend enrichment | Method 內 Python (產 query_id / chart_id / audit / statistics) |
| Layer 3: Persistence | assistant `message.output[]` + serialized `<details type="tool_calls">` (Open WebUI native) |

**LLM 嚴禁輸出**：`id` / `chart_id` / `rendered` / `audit` / 任何 timestamp / 任何 cache key — 簽名上根本不存在這些參數。

---

## Image Attachment Schema

`render_chart` logical chart result shape（backend-generated fields; serialized through Open WebUI native `function_call_output` / `<details type="tool_calls">` path）：

```python
{
    "type": "image",
    "attachment": {
        "id": chart_id,                                  # uuid4().hex
        "url": f"/api/v1/data-analysis/charts/{id}.png",
        "thumb_url": f"/api/v1/data-analysis/charts/{id}.png?thumb=1",
        "mime_type": "image/png",
        "metadata": {
            "chart_type": str,
            "title": str,
            "explanation": {
                "source": str, "method": str,
                "fields": list[str],
                "aggregation": str | None,
                "notes": str | None,
                "statistics": dict,
            },
            "audit": {
                "rendered_at": iso_str,
                "renderer": "matplotlib",
                "raw_row_count": int,
                "query_id": str,
            },
        },
    },
}
```

---

## Bootstrap (built-in DB-seeded)

```python
# backend/open_webui/tools/data_analysis/__init__.py

BUILTIN_TOOL_ID = "builtin:data-analysis"
SYSTEM_USER_ID = "system"

async def register_builtin_data_analysis_tool(app):
    from .tool_module import Tools as DataAnalysisTools
    instance = DataAnalysisTools()
    specs = get_tool_specs(instance)

    source_path = Path(__file__).parent / "tool_module.py"
    content = source_path.read_text()

    existing = await ToolsModel.get_tool_by_id(BUILTIN_TOOL_ID)
    if existing is None:
        await ToolsModel.insert_new_tool(
            user_id=SYSTEM_USER_ID,
            form_data=ToolForm(id=BUILTIN_TOOL_ID, name="Data Analysis (built-in)",
                               content=content,
                               meta={"manifest": {"builtin": True}}),
            specs=specs,
        )
    else:
        await ToolsModel.update_tool_by_id(BUILTIN_TOOL_ID, {"content": content, "specs": specs})

    # CRITICAL: warm cache so runtime uses live module
    app.state.TOOLS[BUILTIN_TOOL_ID] = instance
    # Upstream cache invalidation key — must match DB content
    app.state.TOOL_CONTENTS[BUILTIN_TOOL_ID] = content
```

> Upstream `utils/tools.py:194-198` invalidates `TOOLS[id]` if `TOOL_CONTENTS[id] != tool.content`. Must seed both. 詳見 teaching 版同節 "Why TOOL_CONTENTS too?"。

### Core touch (僅 1 行)

```python
# backend/open_webui/main.py
@app.on_event("startup")
async def _seed_vertical_tools():
    """[core-touch] Vertical workspace tool registration."""
    from open_webui.tools.data_analysis import register_builtin_data_analysis_tool
    await register_builtin_data_analysis_tool(app)
```

Commit prefix `[core-touch]` 標示。

---

## Frontend usage

```ts
const payload = {
    model: selectedModel,
    messages: [...],
    tool_ids: ['builtin:data-analysis'],
    metadata: {
        workspace_type: 'data-analysis',
        selected_dataset_id: $selectedDatasetIdStore,
    },
};
```

Native middleware 自動：
1. 從 `app.state.TOOLS['builtin:data-analysis']` 取 live module
2. 從 DB 取 specs 給 model
3. Model 決定呼叫 → middleware execute（自動注入 `__user__` 等）
4. Result 包進 assistant `message.output[]`，並序列化成 `<details type="tool_calls">` rendering
5. 持久化到 `chat.chat.history.messages[id]`

**Day 1 correction (2026-05-10)**: current Open WebUI frontend does not persist/read `message.toolCalls[]`. Canvas code must derive chart cards from assistant `message.output[]` `function_call` + `function_call_output` pairs, with serialized `<details type="tool_calls">` as display fallback.

---

## System Prompt 要點

```
You are a manufacturing data analyst assistant. Use the provided tools:

1. Always start with `query_dataset`, then act on `query_id`.
2. For visualizations, call `render_chart` with appropriate chart_type:
   control / spc: process monitoring with ±3σ
   pareto: 80/20 contributor
   box: distribution by group
   heatmap: 2D density
   line / bar / scatter / histogram: standard
3. Always include explanation (source, method, fields).
4. For narrative answers, call `summarize_data` or reply directly.
5. Query_id expiration recovery: if render_chart errors contain
   'query_id expired' or 'not found', re-call query_dataset with
   same params, then retry render_chart silently.

Constraints:
- Don't include raw data in text response — chart attachment carries it
- Use selected dataset_id from workspace context
- If query times out, suggest more selective filter
- Auto-recover from expired query_id (rule 5)
```

**Backend 配合**：`render_chart` cache miss 時 raise error 含關鍵字 `query_id expired` 或 `not found`，LLM 看字面字串就能依 rule 5 retry。

---

## Event emission integration

每個 tool method 必須 emit ledger events，詳見 [`event-ledger.brief.md`](./event-ledger.brief.md)：

| Tool | Emit |
|---|---|
| `query_dataset` | `tool.query_dataset.succeeded` 或 `.failed` |
| `render_chart` | `tool.render_chart.succeeded` 或 `.failed` |

範例：
```python
def query_dataset(self, dataset_id, query, max_rows=100, *, __user__=None):
    t0 = time.perf_counter()
    try:
        result = self.repo.execute_query(...)
        query_id = self.query_cache.put(...)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        asyncio.create_task(log_event(
            event_type='tool.query_dataset.succeeded',
            user_id=__user__['id'],
            tool_name='query_dataset', dataset_id=dataset_id,
            duration_ms=duration_ms, success=True,
            payload={'sql': query, 'query_id': query_id,
                     'row_count': result.row_count, 'truncated': result.truncated},
        ))
        return {...}
    except Exception as e:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        asyncio.create_task(log_event(
            event_type='tool.query_dataset.failed',
            user_id=__user__['id'],
            tool_name='query_dataset', dataset_id=dataset_id,
            duration_ms=duration_ms, success=False,
            error_code=type(e).__name__,
            payload={'sql': query, 'error_message': str(e)},
        ))
        raise
```

---

## Acceptance

- [ ] `Tools` class 5 個 method，全 type-hinted + docstring
- [ ] `get_tool_specs(Tools())` 產出 OpenAI function spec 5 條（無 `__*__` 參數）
- [ ] `register_builtin_data_analysis_tool` idempotent（重啟不重複）
- [ ] `app.state.TOOLS['builtin:data-analysis']` 是 live instance（非 DB-exec'd）
- [ ] LLM 從 chat completion 自動 dispatch tool call
- [ ] `render_chart` 回傳的 attachment 在 native ResponseMessage 自動渲染
- [ ] 12 個 P0 events emit 整合（[`event-ledger.brief.md`](./event-ledger.brief.md)）
- [ ] Reload chat → tool calls 從 chat document 還原
- [ ] Branch / regenerate → 舊 tool call 在 sibling，新訊息自有 tool call

---

## Anti-patterns

- ❌ 自定 SSE event → tool call result attachment
- ❌ LLM 輸出 `chartData[]` → server-side cache by `query_id`
- ❌ 手寫 OpenAI JSON schema → type hints + docstring auto-generate
- ❌ `f'card-{index}'` fallback id → backend `uuid4().hex`
- ❌ `message.metadata.result_cards[]` 平行於 native → 用 assistant `message.output[]` / `<details type="tool_calls">`
- ❌ Tool function 同步 await DB log → `asyncio.create_task`
- ❌ 巢狀 dict 參數（`explanation: {...}`）→ flat string params

---

## 跨檔關聯

- 後端結構：[`database-adapter.brief.md`](./database-adapter.brief.md)
- Vertical UX：[`data-analysis-vertical-spec.brief.md`](./data-analysis-vertical-spec.brief.md)
- 前端 wire：[`frontend-spec.brief.md`](./frontend-spec.brief.md)
- Event log：[`event-ledger.brief.md`](./event-ledger.brief.md)
