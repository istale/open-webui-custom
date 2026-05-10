# Open WebUI Module Inventory — Results

> **Status**: ⏳ In progress — fill during Day 1
> **Branch**: `vertical/data-analysis`
> **Started**: <YYYY-MM-DD>
> **Owner**: <agent / person filling this in>
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
- **Status**: ⏳ TODO
- **Required props**: <list — read script section header>
- **Required stores subscribed**: <list>
- **Submit / event hooks**: <e.g. submitPrompt callback, regenerateResponse, ...>
- **Compose strategy**: <how to embed in our 3-panel layout right column>
- **Caveats**: <e.g. expects chatId to be in URL; expects model selection from store>
- **Files read**: <commit-pinned line ranges>

#### `Messages.svelte` + `Message.svelte` + `ResponseMessage.svelte`

- **Path**: `src/lib/components/chat/Messages.svelte`, `src/lib/components/chat/Messages/Message.svelte`, `src/lib/components/chat/Messages/ResponseMessage.svelte`
- **Status**: ⏳ TODO
- **History prop shape**: <`{ currentId, messages: { [id]: { parentId, childrenIds, role, content, ... } } }` — confirm>
- **Tool call rendering**: <how `<details type="tool_calls">` is rendered, where `message.toolCalls[]` is read>
- **Image attachment rendering**: <where `attachment.type === 'image'` is handled>
- **Caveats**: <e.g. assumes `chatId`, hard-codes some routes>

#### `MessageInput.svelte`

- **Path**: `src/lib/components/chat/MessageInput.svelte`
- **Status**: ⏳ TODO
- **Submit signature**: <`submitPrompt(text, options?)` or similar>
- **IME handling**: <confirm `event.isComposing` / `keyCode === 229` is handled — line refs>
- **File attachment hooks**: <does it support drag-drop / file pick?>
- **Caveats**:

### Message Tree / History

- **`history` object structure**: <confirm tree shape and where `buildMessages()` lives>
- **Branching helper**: <regenerate / edit user message — function names>
- **Persistence wire format**: <how `history` round-trips into `chat.chat`>

### Streaming Pipeline

- **`generate_chat_completion` (backend)**: <`backend/open_webui/utils/middleware.py` or `routers/chat.py` — exact path + signature>
- **`createOpenAITextStream` (frontend)**: <`src/lib/apis/streaming/index.ts` — confirm exists, signature>
- **Tool call streaming flow**: <follow `tool_calls` partial → final state in middleware (line refs)>
- **Cancel / abort**: <which AbortController is used, where it propagates>

### Persistence

#### `Chats` model

- **Path**: `backend/open_webui/models/chats.py`
- **Status**: ⏳ TODO
- **Methods we'll use**: <`get_chat_by_id`, `update_chat_by_id`, `create_chat`, `list_chats_by_user_id` ...>
- **`chat.chat` schema (jsonb)**: <document the keys we care about: `history`, `metadata`, `models`, ...>
- **Workspace metadata pattern**: <confirm we can add `metadata.workspace_type` and `metadata.data_analysis.*` without core mod>
- **RBAC integration**: <how `Chats.get_chat_by_id_and_user_id` enforces ownership>

#### Folders

- **Path**: `backend/open_webui/models/folders.py` + `routers/folders.py`
- **Status**: ⏳ TODO
- **API surface**: <create, list, assign chat to folder>
- **Caveats**: <can vertical chats live in a special folder name? auto-created?>

### Auth + RBAC

- **`get_verified_user`**: <`backend/open_webui/utils/auth.py` — confirm signature, what it returns>
- **`get_admin_user`**: <same path — when needed>
- **Token decode**: <`decode_token` location, JWT shape>
- **Cookie / header / query auth**: <confirm Open WebUI accepts cookie + Bearer; clarify whether `<img>` tags can use cookie>
- **Permission groups**: <`backend/open_webui/models/groups.py` — group-based access checks>

### Folder + Chat List

- **Sidebar**: `src/lib/components/layout/Sidebar.svelte`
- **Status**: ⏳ TODO
- **How to add vertical entry**: <slot? hard-coded list? config-driven? — find out>
- **Search API**: <chat search endpoint, vertical filter possible?>

---

## Tier 2 — Reuse If Cheap

### Markdown / Content Rendering

- **`ContentRenderer.svelte`**: <confirm props, slot patterns>
- **`Markdown.svelte`**: <confirm renders code, tables, math>
- **`MarkdownTokens.svelte` reasoning**: <line refs for `<details type="reasoning">`>
- **Decision**: <use as-is | wrap | fork>

### Follow-ups

- **`FollowUps.svelte`**: <props: `followUps: string[]`, `onClick(prompt)`>
- **`generateFollowUps`**: <API path>
- **Decision**:

### Artifacts

- **`Artifacts.svelte`**: <confirm session-level vs message-level>
- **Decision**: ❌ Not suitable for chart canvas (per inventory). Custom `CanvasFeed.svelte`.

### Tool Calling UI

- **`<details type="tool_calls">` rendering**: <line refs>
- **Image attachment via `tool_calls.result.attachment`**: <confirm path from `middleware.py:498` — what shape does ResponseMessage expect?>
- **Decision**:

### Models / Settings

- **`models` store**: <`src/lib/stores/index.ts` — list shape>
- **Model selection UI**: <reuse or hide for vertical? — UX decision>
- **i18n / theme stores**:

---

## Tier 3 — Custom (Open WebUI doesn't have)

### Confirmed Custom

- [ ] `src/routes/(app)/data-analysis/+page.svelte` — 3-panel shell
- [ ] `src/lib/components/data-analysis/DatasetPanel.svelte` — left panel
- [ ] `src/lib/components/data-analysis/CanvasFeed.svelte` — middle panel chart feed
- [ ] `src/lib/components/data-analysis/ChartCardCanvas.svelte` — single canvas card
- [ ] `backend/open_webui/tools/data_analysis/tool_module.py` — class Tools
- [ ] `backend/open_webui/tools/data_analysis/__init__.py` — startup registration
- [ ] `backend/open_webui/utils/data_analysis/repository.py` — Port
- [ ] `backend/open_webui/utils/data_analysis/adapters/in_memory_adapter.py`
- [ ] `backend/open_webui/utils/data_analysis/adapters/http_adapter.py`
- [ ] `backend/open_webui/utils/data_analysis/chart_renderer.py` — matplotlib
- [ ] `backend/open_webui/utils/data_analysis/query_cache.py`
- [ ] `backend/open_webui/routers/data_analysis.py` — chart serving endpoint + dataset list pass-through
- [ ] `backend/open_webui/utils/data_analysis/fixtures.py` — InMemory test data

**Hard cap**: 13 files. If approaching this number, re-check Tier 1/2 for missed reuse.

### Newly Discovered Custom (during inventory)

<append here if you find we need a custom file not in the list above; explain why no native option fits>

---

## Discrepancies Between Spec and Codebase

> Any time the actual codebase contradicts our spec docs, log it here and **stop** to update the spec before proceeding.

| ID | Spec doc | Spec claim | Reality | Resolution | Spec commit |
|----|----------|-----------|---------|------------|-------------|
| D-001 | tools-schema.md | `register_tool(schema, handler)` exists | No such API; tools are DB-stored Python | Updated tools-schema §「整合 Open WebUI 的 Tool Registration」 | `289f106b6` |
| D-002 | | | | | |

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
| **A** native `<Chat>` 已支援 `tool_ids` + `metadata` props | 直接傳 props | 0 | ⏳ |
| **B** 原生 `<Chat>` 不接受這些 props，但走 fetch | service worker / fetch interceptor | medium | ⏳ |
| **C** 原生 `<Chat>` 完全鎖死 | `[core-touch]` 加 2 個 props (`extraToolIds`, `extraMetadata`) | low (1 commit) | ⏳ |

**決策**：<選一個，記在這>

## Sidebar Entry Decision (frontend-spec.md §1.2)

> **必須在 Day 1 確認**：原生 sidebar 怎麼加 vertical entry？

- [ ] Plugin / dynamic registration mechanism exists (preferred)
- [ ] Hard-coded list — requires `[core-touch] Sidebar.svelte`
- [ ] Other mechanism: <describe>

**決策**：

## Native ResponseMessage Image Rendering Hook (frontend-spec.md §6)

> **必須在 Day 1 確認**：原生看到 `tool_calls.result.attachment.type === 'image'` 怎麼渲染？我們要改成 placeholder（小卡片）需要走哪條路？

- [ ] **Path-FE-A**: 原生支援 `attachment.metadata.render_mode = 'placeholder'`
- [ ] **Path-FE-B**: 需 wrap / cascade context
- [ ] **Path-FE-C**: CSS hide + DOM inject
- [ ] **Other**:

**決策**：

## Open Questions

> Things we couldn't determine from code reading alone. Flag for user / domain expert.

- [ ] Q1: <e.g. "Does sidebar support adding workspace entries via plugin or only hard-coded?">
- [ ] Q2:

---

## Day 1 Acceptance

- [ ] All Tier 1 modules read; required props / stores / submit hooks documented
- [ ] All Tier 2 modules: decision recorded (use / wrap / skip)
- [ ] Tier 3 custom file list confirmed at ≤13 files
- [ ] Discrepancies table has zero unresolved entries
- [ ] Open questions surfaced to user
- [ ] Tag: `git tag inventory-done`
- [ ] Stop. Wait for user review before Day 2 (writing the Port).
