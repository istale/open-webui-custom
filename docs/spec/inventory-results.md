# Open WebUI Module Inventory — Results

> **Status**: ✅ Ready for `inventory-done` review checkpoint
> **Branch**: `vertical/data-analysis`
> **Started**: 2026-05-10
> **Owner**: Codex
>
> **Purpose**: Cross-reference [`openwebui-module-inventory.md`](./openwebui-module-inventory.md) tier list against actual codebase. Capture real props / stores / integration strategy. Block on discrepancies before writing application code.
>
> **Rules for filling**:
> - Read the actual file (don't guess from filename)
> - Quote exact `import` paths and prop names
> - Mark each row: ✅ confirmed / ⚠️ caveat / ❌ doesn't fit our use case
> - If a "caveat" or "doesn't fit", drop a note in §Discrepancies at the bottom
> - Commit hourly: `git commit -m "wip: inventory <module-or-tier>"`

---

## Pre-confirmed (already verified, do not re-read unless suspicious)

驗證對象：upstream `f51d2b026`（2026-05-09 sync 後）。Line numbers shifted slightly from earlier `8dae237a0` baseline.

| Item | Status | Reference commit | Note |
|---|---|---|---|
| Tool registration mechanism (DB-stored Python + class Tools) | ✅ confirmed | `289f106b6` re-verified post-sync | structure unchanged |
| `app.state.TOOLS = {}` cache, init at `main.py:982` | ✅ confirmed | post-sync | 原 line 973，shifted |
| **`app.state.TOOL_CONTENTS = {}` cache (NEW upstream)**, init at `main.py:983` | ⚠️ **NEW from upstream sync** | post-sync | Cache invalidation key — registration code MUST also seed `TOOL_CONTENTS[id] = content` 否則 live instance 會被覆蓋（spec 已更新）|
| Tool resolution check (`utils/tools.py:194-198`) | ⚠️ Updated | post-sync | 從 `if module is None` 改成 `if module is None or TOOL_CONTENTS.get(id) != content` |
| `get_tool_specs(module)` auto-generates from type hints + docstrings | ✅ confirmed | post-sync | location: `utils/tools.py:753` |
| `convert_function_to_pydantic_model` | ✅ confirmed | post-sync | location: `utils/tools.py:662` |
| `load_tool_module_by_id` | ✅ confirmed | post-sync | location: `utils/plugin.py:202` (unchanged) |
| `__user__` / `__id__` / `__metadata__` / `__messages__` injection | ✅ confirmed | post-sync | mechanism unchanged |
| `tool_ids` in form_data triggers tool resolution | ✅ confirmed | post-sync | `middleware.py:2549` |
| `payload_tools` (caller-provided tools array) | ✅ confirmed | post-sync | `middleware.py:2463` |
| `Chats` model API surface | ✅ confirmed | post-sync | 100% method signatures unchanged |
| `Sidebar.svelte` 1654 lines | ✅ confirmed unchanged | post-sync | upstream 沒動，Plan A/B/C 仍適用 |
| `Chat.svelte` exports | ⚠️ Refactored (188+/-34 lines) | post-sync | only `chatIdProp` exported still — Plan A 仍可能需 [core-touch] 加 `tool_ids`/`metadata` props |
| `ResponseMessage.svelte` | ⚠️ Refactored (84+/-39 lines) | post-sync | Day 1 inventory 必看新版本 attachment render 路徑 |

---

## Tier 1 — Must Reuse

### Chat Lifecycle Core

#### `Chat.svelte`

- **Path**: `src/lib/components/chat/Chat.svelte`
- **Status**: ⚠️ confirmed with caveats
- **Required props**: only `export let chatIdProp = ''` (`src/lib/components/chat/Chat.svelte:115`). No `tool_ids`, `metadata`, route override, or history prop exists.
- **Required stores subscribed**: imports and uses native stores from `$lib/stores`, including `chatId`, `chatTitle`, `chats`, `models`, `settings`, `temporaryChatEnabled`, `selectedFolder`, `chatRequestQueues`, `toolServers`, `terminalServers`, `socket`, `user`, and others (`src/lib/components/chat/Chat.svelte:1-99`, `src/lib/components/chat/Chat.svelte:2991-3239`).
- **Submit / event hooks**: `MessageInput` dispatches `submit`; Chat handles it at `on:submit` and calls `submitHandler(e.detail)` (`src/lib/components/chat/Chat.svelte:3096-3167`). Message creation flows through `submitPrompt`, `sendMessage`, `sendMessageSocket`, `regenerateResponse`, `continueResponse`, `mergeResponses`, and `stopResponse` (`src/lib/components/chat/Chat.svelte:1906-2044`, `src/lib/components/chat/Chat.svelte:2232-2468`, `src/lib/components/chat/Chat.svelte:2578-2620`, `src/lib/components/chat/Chat.svelte:2725-2755`).
- **Compose strategy**: embed native `<Chat chatIdProp={chatId}>` in the right panel, but plan for a small `[core-touch]` prop extension so the vertical route can inject `extraToolIds` and `extraMetadata` into the existing payload path.
- **Caveats**: `navigateHandler()` resets `selectedToolIds` on every chat load (`src/lib/components/chat/Chat.svelte:193-252`). New chat creation and backend-created chat IDs hard-code `/c/{id}` via `window.history.replaceState` (`src/lib/components/chat/Chat.svelte:2511-2515`, `src/lib/components/chat/Chat.svelte:2768-2795`). `saveChatHandler()` persists `models`, `history`, `messages`, `params`, and `files`, but not arbitrary vertical metadata (`src/lib/components/chat/Chat.svelte:2808-2827`).
- **Files read**: `src/lib/components/chat/Chat.svelte:100-260`, `:1344-1457`, `:1906-2044`, `:2232-2468`, `:2475-2565`, `:2578-2620`, `:2725-2817`, `:2991-3239`.

#### `Messages.svelte` + `Message.svelte` + `ResponseMessage.svelte`

- **Path**: `src/lib/components/chat/Messages.svelte`, `src/lib/components/chat/Messages/Message.svelte`, `src/lib/components/chat/Messages/ResponseMessage.svelte`
- **Status**: ⚠️ confirmed with caveats
- **History prop shape**: ✅ `{ currentId, messages: { [id]: { id, parentId, childrenIds, role, content, output?, files?, embeds?, followUps?, done?, ... } } }`. `Messages.svelte` walks backward from `history.messages[history.currentId]` through `parentId`, reverses the list, and uses `childrenIds` for branch navigation (`src/lib/components/chat/Messages.svelte:27-60`, `src/lib/components/chat/Messages.svelte:85-132`, `src/lib/components/chat/Messages.svelte:191-328`, `src/lib/components/chat/Messages.svelte:503-531`).
- **Tool call rendering**: ✅ native display comes from serialized `<details type="tool_calls">` blocks in `message.content`, not from a frontend `message.toolCalls[]` array. `ResponseMessage` passes `message.content` to `ContentRenderer` (`src/lib/components/chat/Messages/ResponseMessage.svelte:824-849`), then `ContentRenderer` passes tokens through `Markdown` / `MarkdownTokens` (`src/lib/components/chat/Messages/ContentRenderer.svelte:176-213`, `src/lib/components/chat/Messages/Markdown.svelte:63-114`). `MarkdownTokens` routes `details[type=tool_calls]` to `ToolCallDisplay` (`src/lib/components/chat/Messages/Markdown/MarkdownTokens.svelte:57-60`, `src/lib/components/chat/Messages/Markdown/MarkdownTokens.svelte:370-437`).
- **Image attachment rendering**: ✅ user/assistant `message.files` images render in `ResponseMessage.svelte:702-724`. Tool-call files render separately in `ToolCallDisplay.svelte`: it parses `attributes.files` and renders `<Image>` for strings starting `data:image/` or objects where `file.type === 'image'` / `content_type` starts with `image/` and `file.url` exists (`src/lib/components/common/ToolCallDisplay.svelte:79-90`, `src/lib/components/common/ToolCallDisplay.svelte:256-270`).
- **Caveats**: ⚠️ no native placeholder hook was found in `ResponseMessage` or `ToolCallDisplay`. Tool-call output exists structurally on assistant `message.output[]`; the visible chat block is serialized HTML-like content generated by backend middleware.

#### `MessageInput.svelte`

- **Path**: `src/lib/components/chat/MessageInput.svelte`
- **Status**: ✅ confirmed
- **Submit signature**: `MessageInput` dispatches `submit` with the current prompt string (`dispatch('submit', prompt)`), and `Chat.svelte` consumes it as `on:submit={(e) => submitHandler(e.detail)}` (`src/lib/components/chat/MessageInput.svelte:1241-1250`, `src/lib/components/chat/MessageInput.svelte:1546-1550`, `src/lib/components/chat/Chat.svelte:3160-3167`).
- **IME handling**: ✅ `isComposing`, `compositionEndedAt`, and `inOrNearComposition(event)` guard Enter submission, including Safari composition timing (`src/lib/components/chat/MessageInput.svelte:425-449`, `src/lib/components/chat/MessageInput.svelte:1491-1550`).
- **File attachment hooks**: ✅ file picker, upload, drag/drop, and sidebar chat/folder drop are built in. The dropzone attaches `dragover`, `drop`, and `dragleave` listeners to `#chat-pane` (`src/lib/components/chat/MessageInput.svelte:454-460`, `src/lib/components/chat/MessageInput.svelte:591-698`, `src/lib/components/chat/MessageInput.svelte:831-910`, `src/lib/components/chat/MessageInput.svelte:1088-1116`, `src/lib/components/chat/MessageInput.svelte:1204-1217`).
- **Caveats**: selected vertical tool IDs must flow through `selectedToolIds`; current Chat owns this binding locally.

### Message Tree / History

- **`history` object structure**: ✅ tree shape confirmed: `{ messages: {}, currentId: null }` initialized in `Chat.svelte:170-173`; `Messages.svelte` `buildMessages()` reconstructs the visible path from `history.currentId` backward through `parentId` (`src/lib/components/chat/Messages.svelte:85-103`).
- **Branching helper**: ✅ `gotoMessage`, `showPreviousMessage`, and `showNextMessage` navigate siblings via `childrenIds` (`src/lib/components/chat/Messages.svelte:191-328`). User edits/regeneration append new children in Chat helpers such as `submitMessage`, `regenerateResponse`, and `continueResponse` (`src/lib/components/chat/Chat.svelte:2622-2716`).
- **Persistence wire format**: ✅ `loadChat()` reads `chat.chat.history` or falls back to `convertMessagesToHistory(chatContent.messages)` (`src/lib/components/chat/Chat.svelte:1361-1380`). `saveChatHandler()` writes `history` and `messages: createMessagesList(history, history.currentId)` through `updateChatById` (`src/lib/components/chat/Chat.svelte:2808-2817`). Backend `Chats.insert_new_chat` and `Chats.update_chat_by_id` store this dict in `Chat.chat` JSON (`backend/open_webui/models/chats.py:295-333`, `backend/open_webui/models/chats.py:386-399`).

### Streaming Pipeline

- **`generate_chat_completion` (backend)**: ✅ native chat pipeline resolves in `backend/open_webui/utils/middleware.py`; relevant tool payload path starts with `process_chat_payload`-style form mutation around `tool_ids = form_data.pop('tool_ids', None)` and metadata enrichment (`backend/open_webui/utils/middleware.py:2462-2631`), then tool resolution and native function spec injection (`backend/open_webui/utils/middleware.py:2633-2867`).
- **`createOpenAITextStream` (frontend)**: ✅ exists as `createOpenAITextStream(responseBody: ReadableStream<Uint8Array>, splitLargeDeltas: boolean): Promise<AsyncGenerator<TextStreamUpdate>>` (`src/lib/apis/streaming/index.ts:26-41`). Primary chat submit uses task JSON via `generateOpenAIChatCompletion()` (`src/lib/apis/openai/index.ts:362-392`); `createOpenAITextStream` is used for merge/MoA streaming (`src/lib/components/chat/Chat.svelte:2725-2755`).
- **Tool call streaming flow**: ✅ backend appends `function_call` items, emits `chat:completion` with `content: serialize_output(full_output())` and `output: full_output()` (`backend/open_webui/utils/middleware.py:4474-4505`). After execution, `process_tool_result()` converts result/files/embeds (`backend/open_webui/utils/middleware.py:1010-1204`), appends `function_call_output` items (`backend/open_webui/utils/middleware.py:4637-4671`), strips LLM-only input images before frontend emission (`backend/open_webui/utils/middleware.py:4738-4755`), and serializes visible details with `serialize_output()` (`backend/open_webui/utils/middleware.py:457-508`).
- **Cancel / abort**: ✅ task cancellation goes through `stopResponse()`, `stopTasksByChatId()` / `stopTask()`, and `generationController?.abort()` for frontend-only merge streaming (`src/lib/components/chat/Chat.svelte:2578-2620`).

### Persistence

#### `Chats` model

- **Path**: `backend/open_webui/models/chats.py`
- **Status**: ✅ confirmed
- **Methods we'll use**: `insert_new_chat(id, user_id, form_data)`, `update_chat_by_id(id, chat)`, `get_chat_by_id(id)`, `get_chat_by_id_and_user_id(id, user_id)`, `is_chat_owner(id, user_id)`, `update_chat_folder_id_by_id_and_user_id(...)` (`backend/open_webui/models/chats.py:295-333`, `backend/open_webui/models/chats.py:386-399`, `backend/open_webui/models/chats.py:854-899`, `backend/open_webui/models/chats.py:901-905`).
- **`chat.chat` schema (jsonb)**: ✅ backend stores an unconstrained dict in `Chat.chat = Column(JSON)` (`backend/open_webui/models/chats.py:40-56`, `backend/open_webui/models/chats.py:132-134`). Existing frontend uses keys such as `title`, `models`, `history`, `messages`, `params`, `files`, `timestamp`, `system`; vertical can add `metadata` inside this dict.
- **Workspace metadata pattern**: ✅ no model-level restriction blocks `chat.chat.metadata.workspace_type` or `chat.chat.metadata.data_analysis.*`. Caveat: native `Chat.svelte` does not preserve metadata in `createNewChat()` / `saveChatHandler()` today, so the vertical route must write metadata via API or a small Chat prop/core hook.
- **RBAC integration**: ✅ `get_chat_by_id_and_user_id` filters by both `id` and `user_id` (`backend/open_webui/models/chats.py:890-899`); router endpoints use `Depends(get_verified_user)`.

#### Folders

- **Path**: `backend/open_webui/models/folders.py` + `routers/folders.py`
- **Status**: ✅ confirmed
- **API surface**: folder model has `id`, `parent_id`, `user_id`, `name`, `items`, `meta`, `data`, `is_expanded` (`backend/open_webui/models/folders.py:24-35`). `FolderForm` supports `name`, `data`, `meta`, and `parent_id` (`backend/open_webui/models/folders.py:72-77`). Create/list/update helpers exist (`backend/open_webui/models/folders.py:88-123`, `backend/open_webui/models/folders.py:158-191`, `backend/open_webui/models/folders.py:218-263`). Router create is `POST /folders/` (`backend/open_webui/routers/folders.py:106-124`). Chat-to-folder assignment is `POST /chats/{id}/folder` with `folder_id` (`backend/open_webui/routers/chats.py:1482-1498`).
- **Caveats**: ✅ vertical chats can live in a normal folder, but no auto-created vertical folder convention exists. If needed, create it explicitly with `meta`/`data` markers rather than adding a new persistence table.

### Auth + RBAC

- **`get_verified_user`**: ✅ `def get_verified_user(user=Depends(get_current_user))`; allows roles `user` and `admin`, otherwise raises 401 (`backend/open_webui/utils/auth.py:458-464`).
- **`get_admin_user`**: ✅ `def get_admin_user(user=Depends(get_current_user))`; allows only `admin` (`backend/open_webui/utils/auth.py:467-473`).
- **Token decode**: ✅ `decode_token(token: str) -> Optional[dict]` decodes JWT with `SESSION_SECRET` and returns dict or `None`; token payload includes user `id`, `jti`, `iat`, and optional `exp` (`backend/open_webui/utils/auth.py:200-219`).
- **Cookie / header / query auth**: ✅ `get_current_user` accepts Bearer credentials, cookie `token`, and `request.state.token` fallback (`backend/open_webui/utils/auth.py:297-320`). `<img src="/api/...">` can rely on browser cookies if the image endpoint uses `Depends(get_verified_user)`; do not invent token query fallback.
- **Permission groups**: ✅ tool access checks include group membership via `Groups.get_groups_by_member_id(user.id)` and `AccessGrants.has_access(...)` in `get_tools()` (`backend/open_webui/utils/tools.py:165-193`).

### Folder + Chat List

- **Sidebar**: `src/lib/components/layout/Sidebar.svelte`
- **Status**: ⚠️ confirmed with caveats
- **How to add vertical entry**: no dynamic workspace-entry registry or plugin slot found. Pinned top-level items are controlled by `DEFAULT_PINNED_ITEMS`, `isMenuItemVisible()`, and `getMenuItemMeta()` (`src/lib/components/layout/Sidebar.svelte:78-150`), then rendered twice for collapsed/expanded sidebar (`src/lib/components/layout/Sidebar.svelte:859-900`, `src/lib/components/layout/Sidebar.svelte:1107-1150`). Existing chat rows use `ChatItem`, whose anchor hard-codes `href="/c/{id}"` (`src/lib/components/layout/Sidebar/ChatItem.svelte:448-471`).
- **Search API**: ✅ generic chat search exists: frontend `getChatListBySearchText(token, text, page)` calls `GET /api/v1/chats/search?text=...&page=...` (`src/lib/apis/chats/index.ts:353-370`); backend `search_user_chats()` filters by user and text only (`backend/open_webui/routers/chats.py:594-610`). No vertical metadata filter exists.

---

## Tier 2 — Reuse If Cheap

### Markdown / Content Rendering

- **`ContentRenderer.svelte`**: ✅ props confirmed: `id`, `content`, `history`, `messageId`, `selectedModels`, `done`, `model`, `sources`, `save`, `preview`, `floatingButtons`, `editCodeBlock`, `topPadding`, and callbacks (`src/lib/components/chat/Messages/ContentRenderer.svelte:18-40`). No slot extension point; wraps `Markdown` and floating buttons (`src/lib/components/chat/Messages/ContentRenderer.svelte:176-220`).
- **`Markdown.svelte`**: ✅ processes response content, runs `marked.lexer`, and renders `MarkdownTokens`; loaded extensions include code/math/citations/footnotes/mentions/colon fences (`src/lib/components/chat/Messages/Markdown.svelte:1-61`, `src/lib/components/chat/Messages/Markdown.svelte:63-114`).
- **`MarkdownTokens.svelte` reasoning**: ✅ groups `details` types `tool_calls`, `reasoning`, and `code_interpreter`; non-tool details use `Collapsible` (`src/lib/components/chat/Messages/Markdown/MarkdownTokens.svelte:57-60`, `src/lib/components/chat/Messages/Markdown/MarkdownTokens.svelte:370-450`). `ConsecutiveDetailsGroup` counts reasoning/tool/code-interpreter blocks and handles grouped display (`src/lib/components/chat/Messages/Markdown/ConsecutiveDetailsGroup.svelte:45-75`, `src/lib/components/chat/Messages/Markdown/ConsecutiveDetailsGroup.svelte:77-110`).
- **Decision**: ✅ use as-is for markdown/reasoning; do not fork. For vertical chart placeholders, prefer a small focused hook or CSS/injection fallback rather than forking content rendering.

### Follow-ups

- **`FollowUps.svelte`**: ✅ props are `followUps: string[] = []` and `onClick: (followUp: string) => void` (`src/lib/components/chat/Messages/ResponseMessage/FollowUps.svelte:1-9`). `ResponseMessage` renders it for done messages with `message.followUps` and either inserts into input or submits directly depending on settings (`src/lib/components/chat/Messages/ResponseMessage.svelte:1501-1510`).
- **`generateFollowUps`**: ✅ frontend helper exists at `src/lib/apis/index.ts:824-890` but native primary path now runs as a backend background task: `middleware.py` calls `generate_follow_ups()` and emits `chat:message:follow_ups`, then persists `followUps` into the message (`backend/open_webui/utils/middleware.py:3099-3145`; route implementation in `backend/open_webui/routers/tasks.py:234-285`).
- **Decision**: ✅ use native follow-ups as-is; no vertical custom needed for MVP.

### Artifacts

- **`Artifacts.svelte`**: ⚠️ session-level/global UI. It subscribes to `artifactCode`, `artifactContents`, `showArtifacts`, `showControls`, `settings`, and `chatId` stores rather than a single message/tool result (`src/lib/components/chat/Artifacts.svelte:7-14`, `src/lib/components/chat/Artifacts.svelte:92-119`). It renders iframe/svg artifacts from global `artifactContents` (`src/lib/components/chat/Artifacts.svelte:237-259`).
- **Decision**: ❌ Not suitable for chart canvas (per inventory). Custom `CanvasFeed.svelte`.

### Tool Calling UI

- **`<details type="tool_calls">` rendering**: ✅ backend `serialize_output()` emits `<details type="tool_calls" ... files="..." embeds="...">` for `function_call` + `function_call_output` pairs (`backend/open_webui/utils/middleware.py:457-508`). Frontend `MarkdownTokens` passes those attributes to `ToolCallDisplay` (`src/lib/components/chat/Messages/Markdown/MarkdownTokens.svelte:381-389`, `src/lib/components/chat/Messages/Markdown/MarkdownTokens.svelte:429-437`).
- **Image attachment via `tool_calls.result.attachment`**: ❌ no such path exists in current code. `process_tool_result()` only converts local string `data:image/...` into `tool_result_files` and strips those data images from frontend output as LLM-only input images (`backend/open_webui/utils/middleware.py:1126-1133`, `backend/open_webui/utils/middleware.py:4651-4660`, `backend/open_webui/utils/middleware.py:4738-4755`). Frontend-display files must be present in `function_call_output.files`, then `ToolCallDisplay` reads `attributes.files` (`src/lib/components/common/ToolCallDisplay.svelte:83-84`, `src/lib/components/common/ToolCallDisplay.svelte:256-270`).
- **Decision**: ⚠️ reuse native tool-call display for execution/result disclosure. Canvas feed must derive cards from assistant `message.output[]`. Placeholder needs FE-C unless a core hook is later approved.

### Models / Settings

- **`models` store**: ✅ `export const models: Writable<Model[]> = writable([])`; model union is `OpenAIModel | OllamaModel`, both based on `{ id, name, info?, owned_by }` (`src/lib/stores/index.ts:69-75`, `src/lib/stores/index.ts:131-180`).
- **Model selection UI**: ✅ reuse native Chat model selection in MVP; vertical route should not build a separate selector.
- **i18n / theme stores**: ✅ native components use `getContext('i18n')`; stores include `settings`, `theme`, `config`, `user`, `color`-related settings (`src/lib/stores/index.ts:18-20`, `src/lib/stores/index.ts:37-38`, `src/lib/stores/index.ts:84-111`, `src/lib/stores/index.ts:181-240`).

---

## Tier 3 — Custom (Open WebUI doesn't have)

### Confirmed Custom

- [x] `src/routes/(app)/data-analysis/+page.svelte` — 3-panel shell
- [x] `src/lib/components/data-analysis/DatasetPanel.svelte` — left panel
- [x] `src/lib/components/data-analysis/CanvasFeed.svelte` — middle panel chart feed derived from `message.output[]`
- [x] `src/lib/components/data-analysis/ChartCardCanvas.svelte` — single canvas card
- [x] `backend/open_webui/tools/data_analysis/tool_module.py` — class Tools
- [x] `backend/open_webui/tools/data_analysis/__init__.py` — startup registration
- [x] `backend/open_webui/utils/data_analysis/repository.py` — Port
- [x] `backend/open_webui/utils/data_analysis/adapters/in_memory_adapter.py`
- [x] `backend/open_webui/utils/data_analysis/adapters/http_adapter.py`
- [x] `backend/open_webui/utils/data_analysis/chart_renderer.py` — matplotlib
- [x] `backend/open_webui/utils/data_analysis/query_cache.py`
- [x] `backend/open_webui/routers/data_analysis.py` — chart serving endpoint + dataset list pass-through
- [x] `backend/open_webui/utils/data_analysis/fixtures.py` — InMemory test data

**Hard cap**: 13 files. Confirmed count: **13 / 13**. This is also under the user-level Day 1 cap of 15 files.

### Newly Discovered Custom (during inventory)

None discovered during Day 1 inventory.

---

## Discrepancies Between Spec and Codebase

> Any time the actual codebase contradicts our spec docs, log it here and **stop** to update the spec before proceeding.

| ID | Spec doc | Spec claim | Reality | Resolution | Spec commit |
|----|----------|-----------|---------|------------|-------------|
| D-001 | tools-schema.md | `register_tool(schema, handler)` exists | No such API; tools are DB-stored Python | Updated tools-schema §「整合 Open WebUI 的 Tool Registration」 | `289f106b6` |
| D-002 | tools-schema.md, frontend-spec.md, data-analysis-vertical-spec.md, openwebui-module-inventory.md, event-ledger.md | Canvas/cards derive from frontend `message.toolCalls[]` and image `tool_calls.result.attachment` | Current Open WebUI stores tool calls as assistant `message.output[]` `function_call`/`function_call_output` pairs and serializes visible display into `<details type="tool_calls">`; no `message.toolCalls[]` reader or attachment metadata hook found | Updated teaching + brief specs to use `message.output[]` as the source of truth and `<details>` parsing as fallback | `6515d6b57` |

---

## Mockup Layout Interpretation (mockup-analysis.md)

> User-designed mockup `docs/design/3panel-mockup.html` 的 right panel 是 chat history list，不是 live chat。需確認 layout 解讀。

| Plan | Right panel | 備註 | Decision |
|------|-------------|------|----------|
| **A**（**目前採用**）| Native `<Chat>` (live conversation) | 視覺借用 mockup design tokens / 元件，layout 不變 | ✅ |
| **B** | Mockup 原樣：chat history list | 重組 layout，charts 移其他位置 | ⏳ |
| **C** | History list ↔ live Chat 切換 | 雙模式 right panel | ⏳ |

> **2026-05-09 採 Plan A**。Day 1 完成 inventory + 真機測試後若需改變，更新此表。

---

## Native Chat Integration Decision (frontend-spec.md §9)

> **必須在 Day 1 inventory 中確認**：原生 `<Chat>` (src/lib/components/chat/Chat.svelte) 接收哪些 props？支援 `tool_ids` 與 `metadata` 嗎？

| Plan | Triggered when | Effort | Decision |
|------|----------------|--------|----------|
| **A** native `<Chat>` 已支援 `tool_ids` + `metadata` props | 直接傳 props | 0 | ❌ |
| **B** 原生 `<Chat>` 不接受這些 props，但走 fetch | service worker / fetch interceptor | medium | ⚠️ possible but fragile |
| **C** 原生 `<Chat>` 完全鎖死 | `[core-touch]` 加 2 個 props (`extraToolIds`, `extraMetadata`) | low (1 commit) | ✅ selected |

**決策**：**Plan C**. `Chat.svelte` exports only `chatIdProp` (`src/lib/components/chat/Chat.svelte:115`), owns `selectedToolIds` locally (`src/lib/components/chat/Chat.svelte:151`, `src/lib/components/chat/Chat.svelte:2345-2419`), and does not accept external metadata. Plan B could intercept `fetch('/api/chat/completions')`, but it would be URL/body mutation outside the component contract and would not solve native URL replacement or metadata persistence cleanly.

## Sidebar Entry Decision (frontend-spec.md §1.2)

> **必須在 Day 1 確認**：原生 sidebar 怎麼加 vertical entry？

- [ ] Plugin / dynamic registration mechanism exists (preferred)
- [x] Hard-coded list — requires `[core-touch] Sidebar.svelte`
- [ ] Other mechanism: none found in current codebase

**決策**：**Sidebar Plan C**. `Sidebar.svelte` has hard-coded menu metadata (`src/lib/components/layout/Sidebar.svelte:78-150`) and `Sidebar/ChatItem.svelte` hard-codes chat links to `/c/{id}` (`src/lib/components/layout/Sidebar/ChatItem.svelte:448-471`). Add the vertical entry and vertical chat routing through a minimal `[core-touch]` patch, or users will land in generic chat for data-analysis chats.

## Native ResponseMessage Image Rendering Hook (frontend-spec.md §6)

> **必須在 Day 1 確認**：原生看到 tool-call image result 怎麼渲染？我們要改成 placeholder（小卡片）需要走哪條路？

- [ ] **Path-FE-A**: 原生支援 tool-call file/result render hook such as `files[].metadata.render_mode`
- [ ] **Path-FE-B**: 需 wrap / cascade context
- [x] **Path-FE-C**: CSS hide + DOM inject
- [ ] **Other**:

**決策**：**Path FE-C** for MVP without core touch. Native `ToolCallDisplay.svelte` renders images directly from `files` and ignores metadata (`src/lib/components/common/ToolCallDisplay.svelte:256-270`). No Svelte context, slot, registry, or `render_mode` hook was found in `ResponseMessage`, `MarkdownTokens`, or `ToolCallDisplay`. A cleaner FE-B/core hook can be proposed later if CSS/injection proves too brittle.

## Open Questions

> Things we couldn't determine from code reading alone. Flag for user / domain expert.

- [ ] Q1: Approve the Day 2+ expectation that Native Chat Integration Plan C requires a small `[core-touch]` change to `Chat.svelte` for `extraToolIds` / `extraMetadata` and likely a route override for new vertical chats?
- [ ] Q2: Approve Sidebar Plan C as a `[core-touch]` patch so vertical chats route to `/data-analysis/{id}` instead of `/c/{id}`?
- [ ] Q3: Is FE-C acceptable for the MVP placeholder behavior, or should we stop before frontend work and design a small upstream-friendly hook in `ToolCallDisplay.svelte`?

---

## Day 1 Acceptance

- [x] All Tier 1 modules read; required props / stores / submit hooks documented
- [x] All Tier 2 modules: decision recorded (use / wrap / skip)
- [x] Tier 3 custom file list confirmed at ≤13 files
- [x] Discrepancies table has zero unresolved entries
- [x] Open questions surfaced to user
- [x] Tag: `git tag inventory-done` after this inventory commit
- [x] Stop. Wait for user review before Day 2 (writing the Port).
