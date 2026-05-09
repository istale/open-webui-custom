# Data Analysis Vertical Spec — Brief / Contract Version

> **Quick reference of `data-analysis-vertical-spec.md`. 修改本檔時必須同步更新 teaching 版。**

---

## Vertical 範圍

- Domain: 製造業資料分析 (multi-time × multi-space × multi-batch × multi-sample monitoring)
- Scale: 1M–10M rows / query 為常態
- Users: process / quality engineers
- Server-side rendering（matplotlib PNG），desktop fullscreen only

---

## 三 panel layout

| Panel | 職責 | 元件 |
|---|---|---|
| LEFT | Dataset 選擇 + 過濾 + 預覽 metadata | `DatasetPanel.svelte` |
| MIDDLE | 時序圖表 feed（多卡片從上到下、新在底）+ auto-scroll | `CanvasFeed.svelte` |
| RIGHT | Live chat（native `<Chat>`）+ 訊息泡泡 + chart placeholder | Open WebUI native `<Chat>` |

詳見 [`frontend-spec.brief.md`](./frontend-spec.brief.md) §2.

---

## Persistence

- Live state: `chat.chat.metadata.workspace_type = "data-analysis"` 是 discriminator
- Vertical state: `chat.chat.metadata.data_analysis.{ selected_dataset_id, selected_group_filter, search_term }`
- Cards/charts: derived from `message.toolCalls[]`，不另存
- 行為事件: `data_analysis_events` 表（[`event-ledger.brief.md`](./event-ledger.brief.md)）

---

## Tools (5)

| Tool | Priority | 用途 |
|---|---|---|
| `list_datasets` | P0 | 列出可存取 dataset |
| `query_dataset` | P0 | SELECT → query_id + preview |
| `render_chart` | P0 | matplotlib render → image attachment |
| `summarize_data` | P1 | 文字摘要 |
| `get_dataset_schema` | P1 | dataset 欄位 schema |

詳見 [`tools-schema.brief.md`](./tools-schema.brief.md)。

---

## Chart Types (9)

| chart_type | matplotlib pattern | Manufacturing 用途 |
|---|---|---|
| `line` | `ax.plot(x, y, rasterized=True)` | 時序 sensor reading |
| `scatter` | `ax.scatter(x, y, s=4, rasterized=True)` | 跨欄位相關性 |
| `bar` | `ax.bar(x, y)` | 類別比較 |
| `histogram` | `ax.hist(y, bins=...)` | 單變數分佈 |
| `box` | `ax.boxplot(grouped_y)` | 跨組分佈（batch / sensor）|
| `heatmap` | `ax.imshow(pivot)` + colorbar | sensor × time 密度 |
| `control` / `spc` | line + `axhline(mean)` + `axhline(mean ± 3σ)` + legend | 製程監控 USL/LSL |
| `pareto` | `ax.bar(...)` + `twinx()` cumulative line + `axhline(80)` | 缺陷歸因 80/20 |

### Render policy

- 全資料原始渲染（無 downsampling）
- `dpi=120, figsize=(16, 9), bbox_inches='tight'`
- `rasterized=True` for >100k 點
- 同時生 thumbnail (320×180)
- 估時：line 3–8s, scatter 5–15s for 10M points

### Control/SPC special

優先用 dataset metadata 的 `spec_target / spec_usl / spec_lsl`（[`database-adapter.brief.md`](./database-adapter.brief.md) ColumnMeta.semantic），fallback 算 `mean ± 3σ`。

---

## Database Adapter

`DatasetRepository.execute_query(user_id=ctx.user_id)` propagate RBAC 到外部系統。

`ColumnMeta.semantic` 製造業專用 tags：
- `timestamp / sensor_id / batch_id / sample_id / measurement`
- `spec_target / spec_usl / spec_lsl / metadata`

詳見 [`database-adapter.brief.md`](./database-adapter.brief.md)。

---

## Query Cache

```python
# backend/open_webui/utils/data_analysis/query_cache.py

class QueryCache:
    """LRU cache，memory-held DataFrames."""
    def put(self, query_id: str, df: pd.DataFrame, ttl_s: int = 3600) -> None: ...
    def get(self, query_id: str) -> pd.DataFrame | None: ...
```

- TTL 1 hour
- Cache miss → `render_chart` raise `ToolError("query_id expired")`

---

## Permissions

- 全 tool / route 用 `Depends(get_verified_user)`
- `DatasetRepository.execute_query(user_id=ctx.user_id)` 帶 user 識別到外部
- Chart serving `/api/v1/data-analysis/charts/{chart_id}.png`：原生 auth，無自定 token fallback

---

## Frontend Structure

詳見 [`frontend-spec.brief.md`](./frontend-spec.brief.md) §11。10 個檔案 hard cap，~1680 LOC。

---

## Acceptance Criteria

- [ ] `/workspace/data-analysis` 路由顯示三 panel
- [ ] Pick dataset → metadata 顯示 + suggestion update
- [ ] 送「show monthly trend of sensor S12」→ LLM 自動 call query_dataset → render_chart
- [ ] Chart 同時出現在右欄（placeholder + 定位 button）+ 中欄 canvas（完整大圖）
- [ ] 點定位 → 中欄 scroll + highlight
- [ ] 連送 3 種 chart → 中欄 3 張堆疊（最新底部、auto-scroll）
- [ ] 中欄 scroll up > 200px → auto-scroll 暫停 + 「↓ 有新圖表」按鈕
- [ ] Reload → 所有 chart 從 cached PNG 還原（cache miss → regen）
- [ ] 刪 assistant 訊息 → 對應 chart 從 canvas 消失
- [ ] Branch / regenerate → 舊 chart 在 sibling，新 tool call 在 new branch
- [ ] DROP TABLE 等 query → tool error，chat inline 顯示，無 PNG 產生
- [ ] Backend down 中段 → frontend 清楚錯誤訊息，message done，可重試
- [ ] 切 user (RBAC) → 看不到別人 dataset / chart
- [ ] 12 個 P0 events 完整 emit（[`event-ledger.brief.md`](./event-ledger.brief.md)）

---

## Non-Goals (V1)

- ❌ Chart 互動（zoom / hover）— server-rendered PNG，刻意取捨
- ❌ Real-time streaming dataset (live sensor) — V2
- ❌ 跨 user 共同編輯 charts — V2
- ❌ PDF report 匯出 — V2（PNG cache 鋪好路）
- ❌ 圖表標註 / 編輯 — V2

---

## Risks

| Risk | 緩解 |
|---|---|
| 外部系統慢 / 不可用 | Adapter retry × 2 + 30s timeout + health check + chat 內清楚錯誤 |
| LLM 產出非法 SQL | Tool function strict schema + adapter `QueryValidationError` |
| Chart render OOM (10M scatter) | `rows × cols < 100M` enforce + render timeout + fallback summary card |
| Chart cache disk 滿 | LRU nightly job, > 90 天未存取刪（spec 還在可重生） |
| Dataset schema 改 | adapter 重 fetch + tool retry，audit `raw_row_count` delta 偵測 |

---

## Anti-patterns（從上次失敗教訓）

- ❌ 自定 SSE event types（`event: plan` / `event: card`）
- ❌ 自定 message thread component
- ❌ Page-level `resultCards: ResultCard[]` array
- ❌ LLM 期望輸出 `id` / `chart_id` / timestamps
- ❌ `f'card-{index}'` fallback ID → `uuid4().hex`
- ❌ Image endpoint 自定 token fallback
- ❌ Vertical state 另建 DB table → 用 `chat.metadata`（除了 ledger）
- ❌ Tool / route 直接 `httpx.get(...)` → 用 adapter

---

## 跨檔關聯

- Tools: [`tools-schema.brief.md`](./tools-schema.brief.md)
- Adapter: [`database-adapter.brief.md`](./database-adapter.brief.md)
- Frontend: [`frontend-spec.brief.md`](./frontend-spec.brief.md)
- Tokens: [`frontend-design-tokens.brief.md`](./frontend-design-tokens.brief.md)
- Events: [`event-ledger.brief.md`](./event-ledger.brief.md)
- Reuse: [`openwebui-module-inventory.brief.md`](./openwebui-module-inventory.brief.md)
