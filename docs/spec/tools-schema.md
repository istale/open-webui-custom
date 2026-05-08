# Vertical Workspace Tools Schema — 用 Tool Calling 表達 Vertical 需求

> **核心原則**：vertical 想做的「特殊事件」（plan / card / chart / dataset query）一律表達成 **Open WebUI 原生 tool calls**，不自定義 SSE event。
>
> **典範轉移**：你不是「自己寫 streaming + 渲染管線」，你是「**註冊 tools**」，讓原生 chat 用。

---

## 為什麼用 tools 而不是自定 SSE

| 維度 | 自定 SSE event（上次做法）| Tool Calling（這次做法）|
|---|---|---|
| 整合進原生 lifecycle | ❌ 必須補 Phase 3 Hybrid | ✅ 自動，原生支援 |
| 訊息持久化 | ❌ 自寫 metadata schema | ✅ `message.toolCalls[]` 內建 |
| 取消 / 重試 / 中斷 | ❌ 自刻 abort handler + finally | ✅ 原生 streaming infra 處理 |
| Branching / regenerate | ❌ 自定義 metadata 不會跟 message tree | ✅ Tool result 跟 message 綁，branch 自動帶 |
| RBAC / quota | ❌ 自刻權限檢查 | ✅ 走原生 user model + tool permission |
| Schema versioning | ❌ 自管 v1/v2 升級 | ✅ Tool input/output schema 各自版本化 |
| LLM 提示 | ❌ 自寫 prompt 約束 LLM 輸出 JSON | ✅ Function calling spec，model 原生支援 |

**結論**：寫一個自定 streaming pipeline 等於重做 OpenAI 已經幫你做好的東西。

---

## Tools 設計總覽（Manufacturing Data Analysis）

下列 tools 涵蓋上次規格所有功能，全部用原生 function calling 表達：

| Tool | 用途 | 對應上次規格 |
|---|---|---|
| `query_dataset` | 跑 SELECT query 取資料（df） | 上次的 `_query_chart_points_from_dataset` |
| `render_chart` | matplotlib 渲染圖表 → 回傳 image attachment | 上次的 `render_chart_card_image` |
| `summarize_data` | 文字摘要分析（不出圖） | 上次的 `type: summary` cards |
| `list_datasets` | 列出可用 dataset | 上次 `/datasets` endpoint |
| `get_dataset_schema` | 取得 dataset 欄位 schema | 同上 `/datasets/{id}` |

每個 tool 一個 backend function，原生 chat completion pipeline 會自動：
- 在 LLM response 中偵測 tool call → 派發給 backend
- 把結果包回 message.toolCalls / attachments → 前端原生渲染
- Streaming 中段失敗自動 retry / 顯示 error
- 結果跟 message 永久綁定，branching 帶著走

---

## Tool 1: `query_dataset`

### Schema (OpenAI function calling format)

```json
{
  "type": "function",
  "function": {
    "name": "query_dataset",
    "description": "Run a SELECT query against a registered dataset. Returns row count and a 100-row preview. Full DataFrame is held server-side and referenced by query_id for downstream tools (e.g. render_chart).",
    "parameters": {
      "type": "object",
      "required": ["dataset_id", "query"],
      "properties": {
        "dataset_id": {
          "type": "string",
          "description": "Dataset identifier from list_datasets"
        },
        "query": {
          "type": "string",
          "description": "SQL SELECT statement. DROP/UPDATE/DELETE/INSERT/ALTER are rejected."
        },
        "max_rows": {
          "type": "integer",
          "description": "Maximum rows to return for preview (default 100). Full result set retained server-side regardless.",
          "default": 100
        }
      }
    }
  }
}
```

### Backend Implementation Contract

```python
# backend/open_webui/tools/data_analysis/query_dataset.py

def query_dataset(dataset_id: str, query: str, max_rows: int = 100) -> dict:
    # 1. Validate query (SELECT only, timeout 30s)
    validate_safe_select(query)

    # 2. Execute via DB adapter (see database-adapter.md)
    df = db_adapter.execute_query(dataset_id, query, timeout_s=30)

    # 3. Cache full DataFrame server-side under query_id (UUID)
    query_id = uuid4().hex
    query_cache.put(query_id, df, ttl_s=3600)

    # 4. Return summary + preview only (LLM doesn't see full data)
    return {
        "query_id": query_id,
        "row_count": len(df),
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "preview": df.head(max_rows).to_dict(orient="records"),
        "statistics": {
            c: df[c].describe().to_dict()
            for c in df.select_dtypes(include='number').columns
        }
    }
```

### LLM 看到什麼

LLM 看到的回傳是 preview + 統計，**而非千萬點原始資料**。這保護 context window 也保護 token cost。Full DataFrame 透過 `query_id` 在後續 tool 引用。

---

## Tool 2: `render_chart`

### Schema

```json
{
  "type": "function",
  "function": {
    "name": "render_chart",
    "description": "Render a matplotlib chart from a previous query result. Returns a chart attachment that displays inline in the chat and on the analysis canvas.",
    "parameters": {
      "type": "object",
      "required": ["query_id", "chart_type", "x", "y", "title"],
      "properties": {
        "query_id": {
          "type": "string",
          "description": "query_id from a previous query_dataset call"
        },
        "chart_type": {
          "type": "string",
          "enum": ["line", "bar", "scatter", "histogram", "box", "heatmap", "control", "spc", "pareto"]
        },
        "x": {"type": "string", "description": "Column name for x-axis"},
        "y": {"type": "string", "description": "Column name for y-axis"},
        "facet": {"type": "string", "description": "Optional column for facet/subplot"},
        "color": {"type": "string", "description": "Optional column for color encoding"},
        "title": {"type": "string"},
        "explanation": {
          "type": "object",
          "description": "Human-readable description for the chart caption",
          "required": ["source", "method", "fields"],
          "properties": {
            "source": {"type": "string"},
            "method": {"type": "string"},
            "fields": {"type": "array", "items": {"type": "string"}},
            "aggregation": {"type": "string"},
            "notes": {"type": "string"}
          }
        }
      }
    }
  }
}
```

### Backend Implementation Contract

```python
def render_chart(query_id: str, chart_type: str, x: str, y: str,
                  facet: str | None, color: str | None,
                  title: str, explanation: dict) -> dict:
    # 1. Retrieve full DataFrame from query cache
    df = query_cache.get(query_id)
    if df is None:
        raise ToolError("query_id expired or not found; please re-run query_dataset")

    # 2. Render via matplotlib (full data, no downsampling)
    chart_id = uuid4().hex
    image_path = chart_cache.path_for(chart_id)
    render_matplotlib(df, chart_type, x, y, facet, color, title, image_path)

    # 3. Compute statistics for caption
    stats = compute_statistics(df, x, y)

    # 4. Return attachment (Open WebUI native attachment shape)
    return {
        "type": "image",
        "attachment": {
            "id": chart_id,
            "url": f"/api/v1/data-analysis/charts/{chart_id}.png",
            "thumb_url": f"/api/v1/data-analysis/charts/{chart_id}.png?thumb=1",
            "mime_type": "image/png",
            "metadata": {
                "chart_type": chart_type,
                "title": title,
                "explanation": {**explanation, "statistics": stats},
                "audit": {
                    "rendered_at": now_iso(),
                    "renderer": "matplotlib",
                    "raw_row_count": len(df),
                    "query_id": query_id
                }
            }
        }
    }
```

### 前端怎麼渲染

原生 `ResponseMessage.svelte` 看到 `message.toolCalls[i].result.attachment.type === "image"` 就會自動渲染 image。

對於 vertical canvas，前端這樣 derived：

```ts
$: canvasAttachments = messages.flatMap((m) =>
  (m.toolCalls ?? [])
    .filter((tc) => tc.function?.name === 'render_chart')
    .map((tc) => ({
      ...tc.result.attachment,
      messageId: m.id,
      toolCallId: tc.id
    }))
);
```

中間欄就是 `canvasAttachments` 的 feed view。**完全 derived，不存第二份**。

---

## Tool 3: `summarize_data`

### Schema

```json
{
  "type": "function",
  "function": {
    "name": "summarize_data",
    "description": "Generate a textual summary of a query result. Use this for narrative analysis without producing a chart.",
    "parameters": {
      "type": "object",
      "required": ["query_id", "title", "summary"],
      "properties": {
        "query_id": {"type": "string"},
        "title": {"type": "string"},
        "summary": {"type": "string", "description": "Markdown-formatted summary"},
        "key_findings": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Bullet points of key findings"
        }
      }
    }
  }
}
```

### Backend

Trivial — 把 LLM 給的 summary 包成 attachment 或直接放 message content。建議放 content，不需 tool call（除非要加 audit）。

---

## Tool 4: `list_datasets` / Tool 5: `get_dataset_schema`

```json
{"name": "list_datasets", "description": "List all datasets the user has access to.",
 "parameters": {"type": "object", "properties": {}}}

{"name": "get_dataset_schema",
 "description": "Get column schema, sample rows, and statistics for a dataset.",
 "parameters": {"type": "object", "required": ["dataset_id"],
                "properties": {"dataset_id": {"type": "string"}}}}
```

Backend 走 [database-adapter.md](./database-adapter.md) 的 `list_datasets()` / `get_dataset_metadata()`。

---

## System Prompt 設計

LLM 收到的 system prompt 應該說明 vertical 角色 + 把 tool calling flow 講清楚：

```
You are a manufacturing data analyst assistant. The user has selected a dataset
in the workspace. Use the provided tools to answer questions:

1. Always start with `query_dataset` to fetch data, then act on `query_id`.
2. For visualizations, call `render_chart` with the appropriate chart_type:
   - control / spc: process monitoring with ±3σ limits
   - pareto: 80/20 contributor analysis
   - box: distribution comparison across groups
   - heatmap: 2D density (e.g., sensor × time)
   - line / bar / scatter / histogram: standard cases
3. Always provide an `explanation` object so the analyst can verify your method.
4. For narrative answers without a chart, call `summarize_data` or reply directly.

Constraints:
- Never include raw data points in your text response — they're already in the chart attachment.
- Use the user's selected dataset_id from the workspace context.
- If a query times out, suggest a more selective filter.
```

---

## 三層 Schema 紀律仍然適用（但落點不同）

上次的 Layer 1/2/3 結構對應到 tool calling 模式：

| Layer | 對應 |
|---|---|
| Layer 1 — LLM Output Subset | Tool function `parameters` schema（OpenAI function calling spec）|
| Layer 2 — Backend Enrichment | Tool function 的 Python 實作（query_id / chart_id / audit / statistics 都在這層補）|
| Layer 3 — Persistence Format | `message.toolCalls[]` 欄位（Open WebUI 原生 schema，由原生 lifecycle 持久化）|

**LLM 嚴禁輸出**的欄位（id / chart_id / rendered_at / statistics / raw_row_count）在 function 簽名上**根本不存在**，所以 LLM 想塞也塞不進來 → 原生 function calling 比自刻 SSE 多一層保護。

---

## 整合 Open WebUI 的 Tool Registration

```python
# backend/open_webui/tools/data_analysis/__init__.py

from open_webui.tools.registry import register_tool
from .query_dataset import query_dataset, QUERY_DATASET_SCHEMA
from .render_chart import render_chart, RENDER_CHART_SCHEMA
from .summarize_data import summarize_data, SUMMARIZE_DATA_SCHEMA
from .list_datasets import list_datasets, LIST_DATASETS_SCHEMA
from .get_dataset_schema import get_dataset_schema, GET_DATASET_SCHEMA_SCHEMA

DATA_ANALYSIS_TOOLS = [
    (QUERY_DATASET_SCHEMA, query_dataset),
    (RENDER_CHART_SCHEMA, render_chart),
    (SUMMARIZE_DATA_SCHEMA, summarize_data),
    (LIST_DATASETS_SCHEMA, list_datasets),
    (GET_DATASET_SCHEMA_SCHEMA, get_dataset_schema),
]

def register_data_analysis_tools():
    for schema, handler in DATA_ANALYSIS_TOOLS:
        register_tool(
            schema=schema,
            handler=handler,
            workspace_type="data-analysis",  # vertical 隔離
            requires_auth=True
        )
```

> ⚠️ Open WebUI 的 tool registration 機制請參照 inventory 中 `backend/open_webui/utils/...`（待 inventory 時確認實際 API）。如果原生只支援 OpenAI tool format，沿用即可。

---

## Acceptance（如何驗證 tool calling 路徑通了）

- [ ] `list_datasets` 從 LLM prompt 觸發，原生 chat 自動 dispatch 到 backend，結果出現在 `message.toolCalls[0].result`
- [ ] `query_dataset` → `render_chart` 兩個 tool call 串接，`render_chart` 用 `query_id` 取到正確 DataFrame
- [ ] Chart attachment 自動顯示在 chat 內（`ResponseMessage.svelte` 原生渲染）
- [ ] 中間欄 canvas feed 從 `message.toolCalls[].result.attachment` derived
- [ ] Reload chat → tool calls 從 chat document 還原 → 前端重新渲染（無 image url 失效時走 regen endpoint）
- [ ] 取消 streaming 中的 chat → tool call 也被 cancel（原生 abort propagation）
- [ ] 重生 (regenerate) assistant 訊息 → 舊的 tool call 在 sibling branch，新訊息有自己的 tool call

---

## 反 pattern（上次踩過的坑，別再犯）

| 反 pattern | 正解 |
|---|---|
| 自定 `event: card` SSE | 改 tool call result 的 attachment |
| LLM 輸出 `chartData[]` 整段資料 | 不該在 LLM context 裡，用 `query_id` 引用 server-side cache |
| 自寫 `validate_llm_card` + `FORBIDDEN_LLM_KEYS` | 改用 OpenAI function calling 的 strict schema validation（model 原生支援）|
| 自定 `card_id = f'card-{index}'` | Tool result attachment id 一律 `uuid4().hex` |
| `message.metadata.result_cards[]` 平行於原生 message | 改用 `message.toolCalls[]`（原生欄位）|
