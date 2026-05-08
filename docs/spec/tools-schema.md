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

## 整合 Open WebUI 的 Tool Registration（**已實際確認**）

> **Codebase 確認結果（2026-05-08）**：Open WebUI **沒有** `register_tool(schema, handler)` API。實際機制是「DB-stored Python source code + class Tools convention + auto-spec generation」。本節是基於 codebase 實際讀過後的最終契約。

### 機制三件事

1. **Tool 是一個 Python 模組**，匯出 `class Tools`，每個 method = 一個 callable function。
2. **Spec 自動產生**：`get_tool_specs(module)` 用 [convert_function_to_pydantic_model](backend/open_webui/utils/tools.py:659) 從 type hints + docstring 自動產出 OpenAI function spec。**不要手寫 JSON schema**。
3. **Tool 存在 DB**（table `tool`，欄位 `id` / `content` / `specs`），runtime 由 [load_tool_module_by_id](backend/open_webui/utils/plugin.py:202) 從 `app.state.TOOLS` cache 取，cache miss 才從 DB `exec()`。

### 我們的做法：Built-in DB-seeded + Cache-warmed

```python
# backend/open_webui/tools/data_analysis/tool_module.py
"""Data analysis Tools class — exposes vertical capabilities to native chat.

Methods become callable functions. Type hints + docstrings auto-generate
OpenAI function specs. NO manual JSON schema writing.
"""

from typing import Any
from open_webui.utils.data_analysis import get_repository
from open_webui.utils.data_analysis.query_cache import get_query_cache
from open_webui.utils.data_analysis.chart_renderer import render_matplotlib


class Tools:
    """Data analysis vertical workspace — manufacturing forensics."""

    def __init__(self):
        self.repo = get_repository()
        self.query_cache = get_query_cache()

    def list_datasets(self, tags: str = "", __user__: dict = None) -> dict:
        """List datasets the user has access to.

        :param tags: Optional comma-separated tag filter (e.g. "production,line-a").
        :return: Dict with 'items' list of dataset metadata.
        """
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] or None
        items = self.repo.list_datasets(user_id=__user__["id"], tags=tag_list)
        return {"items": [m.to_dict() for m in items]}

    def query_dataset(
        self,
        dataset_id: str,
        query: str,
        max_rows: int = 100,
        __user__: dict = None,
    ) -> dict:
        """Run a SELECT query against a registered dataset.

        Returns row count and a preview. The full DataFrame is held server-side
        and referenced by query_id for downstream tools (e.g. render_chart).

        :param dataset_id: Dataset identifier from list_datasets.
        :param query: SQL SELECT statement. Non-SELECT is rejected.
        :param max_rows: Maximum preview rows in the response (default 100).
        :return: Dict with query_id, row_count, columns, preview, statistics.
        """
        result = self.repo.execute_query(
            dataset_id=dataset_id, sql=query,
            user_id=__user__["id"], max_rows=10_000_000, timeout_s=30,
        )
        query_id = self.query_cache.put(result.df, ttl_s=3600)
        return {
            "query_id": query_id,
            "row_count": result.row_count,
            "columns": list(result.df.columns),
            "preview": result.df.head(max_rows).to_dict(orient="records"),
            "statistics": _compute_statistics(result.df),
        }

    def render_chart(
        self,
        query_id: str,
        chart_type: str,
        x: str,
        y: str,
        title: str,
        explanation_source: str,
        explanation_method: str,
        explanation_fields: str,
        facet: str = "",
        color: str = "",
        explanation_aggregation: str = "",
        explanation_notes: str = "",
        __user__: dict = None,
        __id__: str = None,
    ) -> dict:
        """Render a matplotlib chart from a previous query result.

        Returns an image attachment that displays inline in chat AND on
        the analysis canvas. Supports manufacturing chart types.

        :param query_id: query_id from a previous query_dataset call.
        :param chart_type: One of: line, bar, scatter, histogram, box, heatmap, control, spc, pareto.
        :param x: Column name for x-axis.
        :param y: Column name for y-axis.
        :param title: Chart title.
        :param explanation_source: Data source description (e.g. "Line A, sensor S12, 2024-10").
        :param explanation_method: Statistical method (e.g. "raw timeseries", "mean by batch").
        :param explanation_fields: Comma-separated list of column names referenced.
        :param facet: Optional column for subplot facet.
        :param color: Optional column for color encoding.
        :param explanation_aggregation: Optional aggregation method (sum, mean, count, ...).
        :param explanation_notes: Optional analyst-facing notes.
        :return: Dict with type='image' and attachment metadata for native rendering.
        """
        df = self.query_cache.get(query_id)
        if df is None:
            raise ValueError("query_id expired or not found; please re-run query_dataset")
        # ... matplotlib render via chart_renderer module ...
        return {
            "type": "image",
            "attachment": {
                "id": chart_id,  # uuid4().hex generated server-side
                "url": f"/api/v1/data-analysis/charts/{chart_id}.png",
                "thumb_url": f"/api/v1/data-analysis/charts/{chart_id}.png?thumb=1",
                "mime_type": "image/png",
                "metadata": {
                    "chart_type": chart_type, "title": title,
                    "explanation": {
                        "source": explanation_source,
                        "method": explanation_method,
                        "fields": [f.strip() for f in explanation_fields.split(",") if f.strip()],
                        "aggregation": explanation_aggregation or None,
                        "notes": explanation_notes or None,
                        "statistics": _compute_statistics(df),
                    },
                    "audit": {
                        "rendered_at": now_iso(),
                        "renderer": "matplotlib",
                        "raw_row_count": len(df),
                        "query_id": query_id,
                    },
                },
            },
        }
```

### 為什麼用「flat parameter names」（`explanation_source` 而非巢狀 dict）

OpenAI function calling 的 spec 對巢狀物件支援不一致（Anthropic Claude / OpenAI GPT / Ollama 等 model 解析行為不同）。用 flat string 參數最穩定，backend 內部再組裝成巢狀 metadata。

### Bootstrap：Startup hook 注入到 DB + cache

```python
# backend/open_webui/tools/data_analysis/__init__.py

import inspect
from pathlib import Path
from open_webui.models.tools import Tools as ToolsModel, ToolForm
from open_webui.utils.tools import get_tool_specs

BUILTIN_TOOL_ID = "builtin:data-analysis"
SYSTEM_USER_ID = "system"

async def register_builtin_data_analysis_tool(app):
    """Idempotent registration — safe to call on every startup."""
    from .tool_module import Tools as DataAnalysisTools

    instance = DataAnalysisTools()
    specs = get_tool_specs(instance)

    # Read source for DB record (audit trail / fallback)
    source_path = Path(__file__).parent / "tool_module.py"
    content = source_path.read_text()

    existing = await ToolsModel.get_tool_by_id(BUILTIN_TOOL_ID)
    if existing is None:
        await ToolsModel.insert_new_tool(
            user_id=SYSTEM_USER_ID,
            form_data=ToolForm(
                id=BUILTIN_TOOL_ID,
                name="Data Analysis (built-in)",
                content=content,
                meta={"description": "Manufacturing data analysis vertical workspace tools.",
                      "manifest": {"builtin": True}},
            ),
            specs=specs,
        )
    else:
        await ToolsModel.update_tool_by_id(
            BUILTIN_TOOL_ID,
            {"content": content, "specs": specs}
        )

    # CRITICAL: warm cache so runtime uses live module, NOT DB-exec'd copy
    app.state.TOOLS[BUILTIN_TOOL_ID] = instance
```

### Core touch: `main.py` 一行 startup hook

```python
# backend/open_webui/main.py (around the existing app.state.TOOLS = {} init)

@app.on_event("startup")
async def _seed_vertical_tools():
    """[core-touch] Vertical workspace tool registration."""
    from open_webui.tools.data_analysis import register_builtin_data_analysis_tool
    await register_builtin_data_analysis_tool(app)
```

> 此為唯一允許的 core touch。Commit 訊息加 `[core-touch]` 前綴。

### Frontend：`tool_ids` 用法

```ts
// 在 data-analysis 路由送 chat completion 時：
const payload = {
    model: selectedModel,
    messages: [...],
    tool_ids: ['builtin:data-analysis'],  // 啟用我們的 vertical tools
    metadata: {
        workspace_type: 'data-analysis',
        selected_dataset_id: selectedDatasetId,
    },
};
```

Open WebUI middleware 收到後會自動：
1. 從 `app.state.TOOLS['builtin:data-analysis']` 取 live module
2. 從 DB 取 specs，給 model 看
3. Model 決定呼叫哪個 method
4. Middleware 執行，自動注入 `__user__` / `__id__`
5. 回傳結果包進 `<details type="tool_calls">` 渲染塊
6. 持久化到 `chat.chat.history.messages[id]`

**整套流程零自定義 SSE / 零自定 reducer**。

### 參數注入：`__user__` / `__id__` / `__metadata__` / `__messages__`

Method 簽名上以 `__xxx__` 開頭的參數會被 [`utils/tools.py:194`](backend/open_webui/utils/tools.py:194) 在 spec 自動移除（不出現在 LLM 看到的 schema），然後由 middleware 在 call 前注入。常用：
- `__user__`: `{ "id": str, "name": str, "email": str, ... }`
- `__id__`: 此 tool 的 tool_id（我們的 `builtin:data-analysis`）
- `__metadata__`: chat metadata（含 `workspace_type` / `selected_dataset_id` 等）
- `__messages__`: 完整訊息列表

**Vertical 規格依賴**：`__user__["id"]` 用來呼叫 `DatasetRepository.execute_query(user_id=...)`，把 RBAC 一路 propagate 到外部 dataset 系統。

### Valves（管理員 / 使用者層級設定）

可選：在 Tools class 加 `Valves` (Pydantic) / `UserValves` 子類，admin 與 user 可在 UI 設定值。範例用途：
- 管理員：`max_query_timeout_s`、`max_chart_size`
- 使用者：`preferred_dataset_id`、`default_chart_dpi`

詳細寫法參考其他 builtin tool 範例（升級 inventory 時順便看）。

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
