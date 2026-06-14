# Open WebUI Module Inventory — Brief / Contract Version

> **Quick reference of `openwebui-module-inventory.md`. 修改本檔時必須同步更新 teaching 版。**
>
> **規則**：寫新 module 之前先 grep Open WebUI。能 compose > extend > fork > 重寫。

---

## Tier 1 — 必用（自寫等於背技術債）

### Chat Lifecycle Core
| Module | Path | 整合策略 |
|---|---|---|
| `Chat.svelte` | `src/lib/components/chat/Chat.svelte` | Compose 進右欄 |
| `Messages.svelte` | `src/lib/components/chat/Messages.svelte` | 自動 by Chat |
| `Message.svelte` | `src/lib/components/chat/Messages/Message.svelte` | 自動 |
| `ResponseMessage.svelte` | `src/lib/components/chat/Messages/ResponseMessage.svelte` | **不 fork**，metadata via 注入 hook |
| `MessageInput.svelte` | `src/lib/components/chat/MessageInput.svelte` | Compose |

### Message Tree
- `history` 物件 by Chat.svelte (`{ currentId, messages: { [id]: { parentId, childrenIds, role, content, ... } } }`)
- `buildMessages(history, currentId)` helper
- Vertical metadata 一律放 `message.metadata.{namespace}.*`

### Streaming
- `generate_chat_completion` (backend chat router)
- `createOpenAITextStream` (`src/lib/apis/streaming/index.ts`)
- Tool call streaming infra (native handles partial→final)
- **不寫**自己的 `streamDataAnalysis.ts`

### Persistence
- `Chats` model `backend/open_webui/models/chats.py` — get/update/create/list
- `chat.chat` jsonb 內 `history` + `metadata`
- Workspace state 用 `chat.chat.metadata.workspace_type` + `metadata.{namespace}.*`
- Folder API: `backend/open_webui/models/folders.py`
- **永遠不另建 vertical 表**（除 event ledger）

### Auth + RBAC
- `get_verified_user` from `backend/open_webui/utils/auth.py`
- `decode_token`、`get_admin_user`
- Permission groups: `backend/open_webui/models/groups.py`
- Image endpoint **不**寫自定 token fallback，走原生 cookie session

### Tool System
- 確認位置：`backend/open_webui/utils/tools.py` (`get_tool_specs`, `convert_function_to_pydantic_model`)
- Loading: `backend/open_webui/utils/plugin.py:202` (`load_tool_module_by_id`)
- Middleware: `backend/open_webui/utils/middleware.py:2500-2700` (tool resolution)
- Cache: `app.state.TOOLS = {}` at `main.py:973`
- 詳見 [`tools-schema.brief.md`](./tools-schema.brief.md)

### Sidebar
- `src/lib/components/layout/Sidebar.svelte`
- 加 vertical entry：Day 1 inventory 確認 plugin / hard-code

---

## Tier 2 — 強烈建議用

### Markdown / Content
| Module | Path |
|---|---|
| `ContentRenderer.svelte` | `src/lib/components/chat/Messages/ContentRenderer.svelte` |
| `Markdown.svelte` | 同目錄 |
| `MarkdownTokens.svelte` | 同目錄（含 `<details type="reasoning">`）|

### Follow-ups
- `FollowUps.svelte` (`src/lib/components/chat/Messages/ResponseMessage/FollowUps.svelte`)
- `generateFollowUps` API

### Tool Calling UI
- `<details type="tool_calls">` rendering（native）
- assistant `message.output[]` + serialized `<details type="tool_calls">`（current frontend does not expose `message.toolCalls[]`）
- `message.statusHistory[]`

### Models / Settings
- `models` store
- `ModelSelector.svelte`
- i18n / theme stores

---

## Tier 3 — Custom (open-webui 沒有的才寫)

### Frontend (~14 files cap, 詳見 [frontend-spec.brief.md §11](./frontend-spec.brief.md))
- `+page.svelte` × 2
- `DataAnalysisLayout / DatasetPanel / DatasetRow / DatasetIcon / Resizer / CanvasFeed / ChartCardCanvas / ChatPlaceholder` Svelte 元件
- `scroll-utils.ts`, `data-analysis.ts` store, `data-analysis/index.ts` API client
- `data-analysis-tokens.css`, `data_analysis.json` (i18n)

### Backend
- `backend/open_webui/routers/data_analysis.py` (chart serving, dataset list, events endpoint)
- `backend/open_webui/tools/data_analysis/` (tool_module + bootstrap)
- `backend/open_webui/utils/data_analysis/`：
  - `repository.py` (Port)
  - `adapters/{http,in_memory}_adapter.py`
  - `chart_renderer.py` (matplotlib pipeline)
  - `query_cache.py`
  - `event_logger.py`
  - `fixtures.py`
- `backend/open_webui/models/data_analysis_events.py`
- Migration `backend/open_webui/migrations/versions/<n>_add_data_analysis_events.py`

---

## Day 1 Inventory Checklist

每個 Tier 1 module：
- [ ] 讀過 source code 至少 2 個關鍵檔
- [ ] 能說出 props / 相依 stores / submit hooks
- [ ] 整合策略明確（compose / extend / fork）

每個 Tier 2 module：
- [ ] 決定 use / wrap / skip

Tier 3：
- [ ] **≤ 15 個檔案**（hard cap，超過代表 over-build）

決策必須回答（記在 [`inventory-results.md`](./inventory-results.md)）：
- [ ] Plan A/B/C: native `<Chat>` 是否接受 `tool_ids` + `metadata` props？
- [ ] Sidebar entry: plugin 機制 or hard-code？
- [ ] Path FE-A/B/C: native ResponseMessage image render hook 哪個 path？

---

## Anti-patterns

| Anti-pattern | 正解 |
|---|---|
| 自寫 `MessageThread.svelte` | 用 native `<Chat>` |
| 自定 `event: plan / card` SSE | 用 tool calls |
| 自寫 `streamDataAnalysis.ts` | 原生 chat completion |
| 自定 `metadata.thinking_content` | 原生 `<think>` in content |
| 自定 vertical 表 | `chat.metadata` (除 ledger) |
| 自刻 token fallback | `Depends(get_verified_user)` |
| Page-level `resultCards[]` | 從 assistant `message.output[]` / `<details type="tool_calls">` derive |
| `f'card-{index}'` ID | `uuid4().hex` |

---

## 跨檔關聯

- Tools 機制：[`tools-schema.brief.md`](./tools-schema.brief.md)
- Frontend 契約：[`frontend-spec.brief.md`](./frontend-spec.brief.md)
- DB 邊界：[`database-adapter.brief.md`](./database-adapter.brief.md)
- Day 1 Worksheet：[`inventory-results.md`](./inventory-results.md)
