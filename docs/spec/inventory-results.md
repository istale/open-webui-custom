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

| Item | Status | Reference commit |
|---|---|---|
| Tool registration mechanism (DB-stored Python + class Tools) | ✅ confirmed | `289f106b6` |
| `app.state.TOOLS = {}` cache, init at `main.py:973` | ✅ confirmed | `289f106b6` |
| `get_tool_specs(module)` auto-generates from type hints + docstrings | ✅ confirmed | `289f106b6` |
| `__user__` / `__id__` / `__metadata__` / `__messages__` injection | ✅ confirmed | `289f106b6` |
| `tool_ids` in form_data triggers tool resolution | ✅ confirmed | `289f106b6` |

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
