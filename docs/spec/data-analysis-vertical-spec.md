# Data Analysis Vertical Workspace — Spec

> ⚡ **Quick reference**: [`data-analysis-vertical-spec.brief.md`](./data-analysis-vertical-spec.brief.md) — 純契約。**修改本檔時必須同步更新 brief 版**。
>
> **Vertical**: Manufacturing data analysis (multi-time × multi-space × multi-batch × multi-sample monitoring)
> **Scale**: 1M–10M data points per query is normal
> **Users**: Process / quality engineers reviewing line health, doing forensic analysis, generating reports
>
> 此文件是 vertical-specific 設計規格。**通用設計請見**：
> - [openwebui-module-inventory.md](./openwebui-module-inventory.md) — 用什麼原生模組
> - [tools-schema.md](./tools-schema.md) — 把功能表達成 tool calls
> - [database-adapter.md](./database-adapter.md) — 接外部資料系統的 Port/Adapter

---

## 1. UX 三 panel layout

```
┌──────────────────┬──────────────────────────────┬──────────────────┐
│ LEFT             │ MIDDLE                       │ RIGHT            │
│ Dataset panel    │ Analysis canvas (chart feed) │ Native Chat      │
│                  │                              │                  │
│ - Group filter   │ Time-ordered chart feed      │ MessageInput     │
│ - Search         │ ↓ auto-scroll on new chart   │ Messages         │
│ - Dataset list   │ (200px deviation rule)       │ ↓ auto-scroll    │
│ - Selected meta  │                              │                  │
│   - rows/cols    │ Each card:                   │ Each chart-type  │
│   - schema       │  - Full PNG (1920x1080)      │ tool call shows  │
│   - tags         │  - Title                     │ a placeholder:   │
│                  │  - Caption (explanation)     │ "📊 Added to     │
│                  │  - Source / method / fields  │  canvas — 定位"  │
│                  │  - Statistics                │                  │
│                  │  - message_id (debug)        │ Summary tool     │
│                  │                              │ calls → inline   │
└──────────────────┴──────────────────────────────┴──────────────────┘
```

### Persistence model
- The whole workspace is a chat in Open WebUI's native `chats` table
- Discriminator: `chat.chat.metadata.workspace_type = "data-analysis"`
- Workspace state in `chat.chat.metadata.data_analysis.{...}`:
  - `selected_dataset_id`
  - `selected_group_filter`
  - `search_term`
- Cards are derived from `message.toolCalls[]` results — no separate storage

### Why time-ordered feed (not pinning / tabs)
> 製造業分析 = 一步步收斂的推理過程，每一步都是 audit trail，**不可隱藏**

## 2. Vertical Tools

See [tools-schema.md](./tools-schema.md). Implementation roster:

| Tool | Priority | Notes |
|---|---|---|
| `list_datasets` | P0 | day 4 |
| `query_dataset` | P0 | day 5 |
| `render_chart` | P0 | day 5 |
| `summarize_data` | P1 | day 6 |
| `get_dataset_schema` | P1 | day 6 |

### Manufacturing-specific chart_type details

| chart_type | matplotlib pattern | Use case |
|---|---|---|
| `line` | `ax.plot(x, y, rasterized=True)` | Time series sensor reading |
| `scatter` | `ax.scatter(x, y, s=4, rasterized=True)` | Cross-feature correlation |
| `bar` | `ax.bar(x, y)` | Categorical comparison |
| `histogram` | `ax.hist(y, bins=...)` | Single-variable distribution |
| `box` | `ax.boxplot(grouped_y)` | Distribution across groups (batch / sensor) |
| `heatmap` | `ax.imshow(pivot)` + colorbar | Sensor × time density |
| `control` / `spc` | line + `axhline(mean)` + `axhline(mean ± 3σ)` + `legend` | Process monitoring with USL/LSL |
| `pareto` | `ax.bar(...)` + `ax2 = ax.twinx()` cumulative line + `axhline(80)` | Defect attribution / 80-20 |

### Render policy
- **No downsampling** — full data rendered
- `dpi=120`, `figsize=(16, 9)`, `bbox_inches='tight'`
- `rasterized=True` for scatter/line with >100k points (avoid PDF/SVG vector overflow)
- Generate thumbnail (320×180) at the same time
- Estimated time: line 3–8s, scatter 5–15s for ~10M points (acceptable in tool-call latency)

## 3. Database Adapter Configuration

See [database-adapter.md](./database-adapter.md).

For this vertical:

```python
# DTO column semantic tags expected from external system
ColumnMeta.semantic ∈ {
    'timestamp',        # required for time-series charts
    'sensor_id',        # facet candidate
    'batch_id',         # facet candidate
    'sample_id',        # group_by candidate
    'measurement',      # y-axis candidate
    'spec_target',      # for control/SPC center line
    'spec_usl',         # upper spec limit
    'spec_lsl',         # lower spec limit
    'metadata'          # generic descriptive
}
```

`render_chart` for `control`/`spc` MUST look up `spec_target / usl / lsl` columns from the dataset metadata if present, falling back to `mean ± 3σ` calculated.

## 4. Query Cache (server-side, vertical-internal)

`query_dataset` returns a `query_id`; subsequent `render_chart(query_id=...)` retrieves the full DataFrame.

```python
# backend/open_webui/utils/data_analysis/query_cache.py

class QueryCache:
    """LRU cache keyed by query_id, holding full DataFrames in memory."""

    def __init__(self, max_size_mb: int = 4096):
        self._cache: dict[str, pd.DataFrame] = {}
        self._access_times: dict[str, float] = {}
        self._max_size_mb = max_size_mb

    def put(self, query_id: str, df: pd.DataFrame, ttl_s: int = 3600) -> None:
        # evict if over budget
        ...

    def get(self, query_id: str) -> pd.DataFrame | None:
        ...
```

TTL = 1 hour. If `render_chart` gets cache miss, raise `ToolError("query_id expired; please re-run query_dataset")`.

## 5. Permissions

- All tools and routes use `Depends(get_verified_user)`.
- `DatasetRepository.execute_query(user_id=ctx.user_id)` propagates user identity to external system.
- Chart serving endpoint `/api/v1/data-analysis/charts/{chart_id}.png`:
  - Validates user via Open WebUI's standard auth (cookie or Bearer)
  - Looks up the chat that owns the chart, verifies user has access to that chat
  - Native auth flow — no custom token fallback (lesson from previous attempt)

## 6. Frontend Structure

> **完整前端規格見 [frontend-spec.md](./frontend-spec.md)**。本節僅給高階概觀。

```
src/routes/(app)/workspace/data-analysis/
├── +page.svelte                  # welcome / new-analysis 入口（無 chat id）
└── [id]/+page.svelte             # 帶 chat id 的工作區

src/lib/components/data-analysis/
├── DataAnalysisLayout.svelte     # 三 panel grid（responsive）
├── DatasetPanel.svelte           # left
├── CanvasFeed.svelte             # middle (derived from message.toolCalls[])
├── ChartCardCanvas.svelte        # single chart card
├── ChatPlaceholder.svelte        # in-chat 「📊 已加到分析畫布」
└── scroll-utils.ts               # auto-scroll helper

src/lib/stores/data-analysis.ts   # selectedDatasetId / datasets / workspaceEvents
src/lib/apis/data-analysis/       # endpoint wrappers
```

- Right-panel `<Chat>` is `import Chat from '$lib/components/chat/Chat.svelte'` — **native, unmodified**
- Pass `tool_ids={['builtin:data-analysis']}` and `metadata={{ workspace_type: 'data-analysis', ... }}`
- `CanvasFeed` derives from `$: messages` of the active chat → flatMap toolCalls → filter render_chart results
- 前端 hard cap：~1400 行，10 個檔案（詳見 [frontend-spec.md §11](./frontend-spec.md#11-frontend-custom-檔案清單tier-3)）

## 7. Acceptance Criteria

- [ ] Open the data-analysis route → 3-panel layout renders
- [ ] Pick a dataset → metadata shown left, prompt suggestions update
- [ ] Send "show monthly trend of sensor S12" → LLM calls `query_dataset` then `render_chart`
- [ ] Chart appears in chat (placeholder + 定位 button) AND in middle canvas (full image)
- [ ] Click 定位 → middle canvas scrolls to that chart with highlight
- [ ] Send 3 different chart prompts → middle canvas shows 3 stacked, newest at bottom, auto-scrolled
- [ ] Scroll up in canvas > 200px → auto-scroll suspended, "↓ 有新圖表" button appears on new card
- [ ] Reload page → all charts re-render from cached PNG (or regen from spec on cache miss)
- [ ] Delete an assistant message → corresponding chart disappears from canvas
- [ ] Branch / regenerate → old chart on sibling branch, new tool call on new branch
- [ ] Try non-SELECT query (e.g. DROP TABLE) → tool returns error, chat shows error inline, no PNG generated
- [ ] Backend goes down mid-stream → frontend shows clear error tail, message marked done, can retry
- [ ] Switch user (different RBAC) → cannot see other user's dataset / charts

## 8. Non-Goals (for V1)

- ❌ Custom chart interactivity (zoom / hover) — server-rendered PNG, deliberate trade-off
- ❌ Real-time streaming dataset (live sensor feed) — V2
- ❌ Cross-user collaboration on charts — V2
- ❌ Export to PDF report — V2 (PNG cache makes this trivial later)
- ❌ Edit / annotate charts — V2

## 9. Risks

| Risk | Mitigation |
|---|---|
| External data system slow / unavailable | Adapter retries (×2), 30s timeout, health check, clear error in chat |
| LLM produces invalid SQL | Tool function strict schema + adapter raises `QueryValidationError` mapped to ToolError |
| Chart render OOM (10M points scatter) | Adapter enforces `rows × cols < 100M`, render has timeout, fallback to summary card |
| Chart cache disk fills | LRU cleanup nightly, > 90 days unused → delete (spec preserved, can regen) |
| Dataset schema changes silently | Adapter can re-fetch metadata; tool retries with refreshed schema; raw_row_count delta detection in audit |

## 10. Anti-patterns to Avoid (carried from previous attempt)

- ❌ Custom SSE event types (`event: plan` / `event: card`)
- ❌ Custom message thread component (`MessageThread.svelte`)
- ❌ Page-level `resultCards: ResultCard[]` array
- ❌ LLM expected to output `id` / `chart_id` / `rendered` / timestamps
- ❌ `f'card-{index}'` style fallback IDs (use `uuid4().hex`)
- ❌ Custom token fallback chains in image endpoint
- ❌ Vertical state in a separate DB table (use `chat.chat.metadata`)
- ❌ Direct `httpx.get(...)` in tool / route code (use adapter)
