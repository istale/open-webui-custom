# Open WebUI Module Inventory — Reuse-First Audit

> ⚡ **Quick reference**: [`openwebui-module-inventory.brief.md`](./openwebui-module-inventory.brief.md) — 純契約。**修改本檔時必須同步更新 brief 版**。
>
> **目的**：在寫第一行 vertical workspace code 之前，把 Open WebUI 既有可重用模組全部列出來。每個模組標記 Tier、整合策略、相依性深度。
>
> **規則**：能 compose 就不要 extend，能 extend 就不要 fork，能 fork 就不要重寫。
>
> **起源**：上一次 data-analysis 專案因為直接寫 custom 元件，導致 Phase 3 整個花在做「native 補救」。Inventory 一次做好 = 省 30%+ 工時。

---

## Tier 1 — 必用（自己寫等於背 6 個月技術債）

### Chat Lifecycle Core

| 模組 | 路徑 | 你拿它做什麼 | 整合策略 | 相依 |
|---|---|---|---|---|
| `Chat.svelte` | `src/lib/components/chat/Chat.svelte` | 整個 chat session 容器；管 socket / streaming / history / model selection | **Compose**：當作右欄子元件嵌進 vertical layout | `chats` / `models` / `user` stores |
| `Messages.svelte` | `src/lib/components/chat/Messages.svelte` | 訊息列表 + auto-scroll + branching navigation | Compose 進 Chat 即可，不要單獨用 | `history` prop（tree 結構） |
| `Message.svelte` | `src/lib/components/chat/Messages/Message.svelte` | Router：派發 user / response / multi-response | 透過 Messages.svelte 自動使用 | — |
| `ResponseMessage.svelte` | `src/lib/components/chat/Messages/ResponseMessage.svelte` | 單一 assistant 訊息渲染：content / sources / tool calls / artifacts / followups | **不要 fork**。Vertical 自訂內容透過 `message.metadata` 附加，原生不讀就用 slot/wrapper 補 | 多 stores |
| `MessageInput.svelte` | `src/lib/components/chat/MessageInput.svelte` | 輸入框 + IME guard + 送出 + 附件 | Compose | `submitPrompt` callback |

**為什麼不可自寫**：
- 自寫的 `MessageThread.svelte` 失去 branching、follow-up 整合、原生 IME guard、原生 markdown / code highlight
- 自寫的 keydown 處理（Enter / Shift+Enter）會漏 IME composition → 中日韓使用者送字到一半就送出
- 自寫的 streaming 沒有原生的 retry、cancel、socket reconnect

### Message Tree / History

| 模組 | 路徑 | 你拿它做什麼 |
|---|---|---|
| `history` 物件 | 由 Chat.svelte 維護 | `{ currentId, messages: { [id]: { parentId, childrenIds, role, content, ... } } }` |
| Message tree helpers | `src/lib/utils/index.ts` 內 | `buildMessages(history, currentId)` 沿 parentId 還原線性訊息 |
| Branching support | Messages.svelte 內建 | regenerate / edit user message 自動建 sibling node |

**Vertical 怎麼用**：你的 vertical-specific data（cards / dataset selection / chart references）一律存 `message.metadata.{vertical_namespace}.*`。永遠不要建另一份 `messages: ChatMessage[]`。

### Streaming Pipeline

| 模組 | 路徑 | 你拿它做什麼 |
|---|---|---|
| `generate_chat_completion` | `backend/open_webui/routers/chat.py` 或 `utils/chat.py` | Backend 主要 chat completion entry，已含 model dispatch / tool calling / streaming |
| `createOpenAITextStream` | `src/lib/apis/streaming/index.ts` | OpenAI-compat SSE chunk 解析器，吐 delta content 給前端 |
| Tool call streaming infra | 同上（內建） | 原生支援 tool call 的 partial / final state、streaming 中斷處理 |

**Vertical 怎麼用**：不要自寫 `streamDataAnalysis.ts`。Vertical 想表達的「特殊事件」（plan / card / chart）改用 **tool calls**（見 [tools-schema.md](./tools-schema.md)）。

### Persistence

| 模組 | 路徑 | 用途 |
|---|---|---|
| `Chats` model | `backend/open_webui/models/chats.py` | DB CRUD：`get_chat_by_id`, `update_chat_by_id`, `create_chat`, list, search |
| `chat.chat` field | DB 內 jsonb | 整個 history tree + metadata 都存這欄位 |
| Folders | `backend/open_webui/models/folders.py` + routes | Chat 分類 |
| `metadata.workspace_type` | 自定 metadata 欄位（已有先例） | discriminator，不同 workspace 用同一張 chats 表 |

**Vertical 怎麼用**：你的 workspace state（dataset selection / canvas state）存 `chat.chat.metadata.{workspace_type}.*`。一張 chat 可以是 generic chat、data-analysis、或未來其他 vertical，靠 `workspace_type` 切換 UI。**永遠不要自建 `analysis_workspaces` 表**。

### Auth + RBAC

| 模組 | 路徑 | 用途 |
|---|---|---|
| `Users` model | `backend/open_webui/models/users.py` | User CRUD、role |
| `get_verified_user` | `backend/open_webui/utils/auth.py` | FastAPI Depends — token 驗證 + user 取得 |
| `decode_token` | 同上 | JWT 解析 |
| `get_admin_user` | 同上 | admin-only routes |
| Permission groups | `backend/open_webui/models/groups.py` | RBAC 基礎 |

**Vertical 怎麼用**：所有 backend route 加 `user=Depends(get_verified_user)`。**不要自刻 token fallback**（上次 image endpoint 三層 fallback 是反例 — 應改用原生 cookie / session 機制）。

### Folder + Chat List

| 模組 | 路徑 | 用途 |
|---|---|---|
| Folder API | `src/lib/apis/folders/index.ts` + backend | 分類資料夾管理 |
| Chat list / search | `src/lib/components/layout/Sidebar.svelte` | 既有 sidebar，可加 vertical filter |
| Chat search API | backend | 跨 chat 搜尋 |

---

## Tier 2 — 強烈建議用（整合便宜）

### Markdown / Content Rendering

| 模組 | 路徑 | 用途 |
|---|---|---|
| `ContentRenderer.svelte` | `src/lib/components/chat/Messages/ContentRenderer.svelte` | Wrap Markdown.svelte，加複製按鈕、code block actions |
| `Markdown.svelte` | `src/lib/components/chat/Messages/Markdown.svelte` | Markdown 解析 + render |
| `MarkdownTokens.svelte` | 同目錄 | Token 級別渲染，含 reasoning collapsible (`<details type="reasoning">`) |

**Vertical 怎麼用**：assistant 文字回覆不要自己渲染。Reasoning / thinking block 用原生 `<details type="reasoning">` 而不是自定 `metadata.thinking_content`。

### Follow-ups

| 模組 | 路徑 | 用途 |
|---|---|---|
| `FollowUps.svelte` | `src/lib/components/chat/Messages/ResponseMessage/FollowUps.svelte` | 建議追問列表 |
| `generateFollowUps` | `src/lib/apis/index.ts` | LLM 生成 follow-up |

### Artifacts / Side Panels

| 模組 | 路徑 | 用途 | 適不適合 vertical canvas |
|---|---|---|---|
| `Artifacts.svelte` | `src/lib/components/chat/Artifacts.svelte` | Code / HTML / SVG side preview | **不適合** chart canvas — Artifacts 是 session-level 而非 message-level，且只認 HTML/code |
| 替代方案 | — | 自寫 `<CanvasFeed>` 但 derived from `message.metadata` | 屬於 Tier 3 custom |

### Tool Calling UI

| 模組 | 路徑 | 用途 |
|---|---|---|
| Tool call display in `ResponseMessage` | 內建 | 顯示 tool 執行中、執行結果、attachments |
| assistant `message.output[]` + `<details type="tool_calls">` | 訊息結構內 | 結構化儲存 tool 呼叫與結果；Day 1 confirmed current frontend does not expose `message.toolCalls[]` |
| `message.statusHistory[]` | 訊息結構內 | 中間進度 |

**Vertical 怎麼用**：每張 chart card / table 表達為「**一次 tool call 的結果**」。詳見 [tools-schema.md](./tools-schema.md)。

### Models / Settings

| 模組 | 路徑 | 用途 |
|---|---|---|
| `models` store | `src/lib/stores/index.ts` | 可用 model 列表 |
| Model selector | `src/lib/components/chat/ModelSelector.svelte` | UI |
| User settings / preferences | `src/lib/stores/index.ts` 內 | i18n、theme、shortcuts |

---

## Tier 3 — Custom（Open WebUI 真的沒有，這才是你寫新 code 的地方）

只有以下範圍需要 custom 寫：

| 元件 | 路徑（建議） | 為什麼必須 custom |
|---|---|---|
| Three-panel layout shell | `src/routes/(app)/{vertical}/+page.svelte` | open-webui 預設是單欄 chat，三 panel 是 vertical 特有 |
| Dataset 選擇器 / 預覽 | `src/lib/components/{vertical}/DatasetPanel.svelte` | manufacturing 資料 schema 與 dataset metadata 是 domain 專屬 |
| Canvas feed | `src/lib/components/{vertical}/CanvasFeed.svelte` | 時序圖表流，是 vertical UX 創新 |
| Chart spec → renderer 後端 | `backend/open_webui/utils/{vertical}/chart_renderer.py` | matplotlib + 製造業特殊 chart_type（control / spc / pareto）|
| Render endpoint | `backend/open_webui/routers/{vertical}.py` | 圖檔 serving + dataset 操作 |
| Database adapter | `backend/open_webui/utils/{vertical}/db_adapter.py` | 與外部 standalone DB 系統溝通（見 [database-adapter.md](./database-adapter.md)）|
| Vertical-specific stores | `src/lib/stores/{vertical}.ts` | dataset selection、canvas scroll 等 ephemeral state |

**判準**：寫之前先問「open-webui 有沒有」。如果有 80% 像的，先試 compose 它，**custom 是最後手段**。

---

## Inventory 完成檢查表

開新 vertical 前，這份 inventory 必須有以下產出：

- [ ] 每個 Tier 1 模組你都讀過 source code 至少 2 個關鍵檔案
- [ ] 每個 Tier 1 模組你能說出它的 props 與相依 stores
- [ ] 你有跑過 git grep 確認沒有「我以為要 custom 但其實已經有」的東西
- [ ] 三個整合策略（compose / extend / fork）每個 Tier 2 模組都有明確標記
- [ ] Tier 3 的 custom 元件清單**不超過 8 個檔案**（超過代表你還在 over-build）

---

## 反 pattern（上次踩過的坑）

| 反 pattern | 為什麼錯 |
|---|---|
| 自寫 `MessageThread.svelte` | 失去 branching、follow-up 整合、IME、原生 markdown |
| 自定 `event: plan / card` SSE | 應改 tool calls — 失去原生 retry / cancel / streaming infra |
| 自寫 `streamDataAnalysis.ts` | 同上，重做了原生 chat completion pipeline |
| 自定 `metadata.thinking_content` | 應改 `<think>` in content + 原生 reasoning rendering |
| 自定 `analysis_workspaces` 表 | 應改 `chat.chat.metadata.workspace_type` |
| Image endpoint 三層 token fallback | 應走原生 cookie session / file attachment 機制 |
| Page-level `resultCards[]` 陣列 | 應一律從原生 assistant `message.output[]` / `<details type="tool_calls">` derived |
