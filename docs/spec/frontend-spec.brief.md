# Frontend Spec — Brief / Contract Version

> **Quick reference of `frontend-spec.md`. Read teaching version for concepts and reasoning.**
> 修改本檔時必須同步更新 `frontend-spec.md`。

---

## 1. Routing

### URLs
| URL | Layout | Mounted |
|---|---|---|
| `/` | Open WebUI native | Home |
| `/c/{id}` | Open WebUI native chat | Generic chat |
| `/workspace/data-analysis` | **3-panel (vertical welcome)** | Pre-chat 歡迎頁 |
| `/workspace/data-analysis/{id}` | **3-panel (vertical with chat)** | Active vertical chat |

### File structure
```
src/routes/(app)/workspace/data-analysis/
├── +layout.svelte          # 三欄 wrap (DataAnalysisLayout)
├── +page.svelte            # 歡迎頁，無 active chat
└── [id]/+page.svelte       # active vertical chat
```

### Sidebar entry — Plan A/B/C decision
依 [`inventory-results.md` Sidebar Entry Decision](./inventory-results.md) 選一：
- A: 動態註冊機制（0 core touch）
- B: config 擴展（`[core-touch]` 改 config）
- C: hard-code（`[core-touch]` 改 `Sidebar.svelte`）

### "+ New Chat" behaviors
| Button | URL after click | Chat type |
|---|---|---|
| Sidebar `+ New Chat`（原生）| `/` | generic |
| Sidebar `📊 Data Analysis` | `/workspace/data-analysis` | — (僅進歡迎頁) |
| 歡迎頁送第一句訊息 | `/workspace/data-analysis/{id}` | **vertical** |

### Vertical vs generic chat 區分
- Discriminator: `chat.chat.metadata.workspace_type === 'data-analysis'`
- 視覺區分：icon 前綴（📊）+ optional auto-folder（待 inventory 確認）
- Sidebar click handler 必須路由到對應路徑

### Step-by-step user flow (含 event emit)

| Step | User 動作 | URL | Event |
|---|---|---|---|
| 1 | 開 app | `/` | — |
| 2 | 點 sidebar 「📊 Data Analysis」 | `/workspace/data-analysis` | `workspace.opened` |
| 3 | dataset 列表載入 | 同上 | — |
| 4 | 選 dataset | 同上 | `dataset.selected` |
| 5 | 送第一句 | `/workspace/data-analysis/{id}` | `prompt.submitted` |
| 6a | model thinking 結束 | 同上 | `model.thinking_completed` |
| 7 | tool query_dataset | 同上 | `tool.query_dataset.{succeeded,failed}` |
| 8 | tool render_chart | 同上 | `tool.render_chart.{succeeded,failed}` |
| 9 | canvas card mount | 同上 | `chart.rendered` |
| 10 | message done | 同上 | `message.assistant_completed` |
| 12 | 點 follow-up | 同上 | `followup.clicked` + `prompt.submitted` |
| ⚠ | streaming idle 30s | 同上 | `stream.timeout` |
| ⚠ | user abort | 同上 | `stream.aborted` |

詳見 [`event-ledger.brief.md`](./event-ledger.brief.md) P0 Events 表。

### Anti-patterns
- ❌ 全域 store 記 vertical mode → 用 `$page.url.pathname`
- ❌ `+layout.svelte` 內 `goto()` → 用 `+layout.ts.load()`
- ❌ Page-level `cards: Card[]` → derived from `history.messages[].toolCalls[]`
- ❌ 自定 SSE event → tool calling
- ❌ Mutate native stores → 用原生 API
- ❌ Sidebar 點 vertical chat 跳 `/c/` → 偵測 metadata 切路徑
- ❌ `window.location.href` → `goto()` from `$app/navigation`

---

## 2. Component Tree

```
+page.svelte (or [id]/+page.svelte)
└── DataAnalysisLayout
    ├── slot=left   → DatasetPanel
    ├── slot=middle → CanvasFeed
    └── slot=right  → <Chat> (Open WebUI native)
```

### `<DataAnalysisLayout>`
```ts
export let leftWidth: number = 300;     // 200–560 clamp
export let rightWidth: number = 480;    // 320–640 clamp
// slots: left, middle, right
// resizers between L↔M and M↔R, widths persisted to localStorage
```

### `<DatasetPanel>`
```ts
export let chatId: string | null;
export let selectedDatasetId: string;
export let datasets: DatasetMeta[];
export let activeGroupFilters: string[] = [];
// Events: select-dataset / toggle-group-filter / reset-filters / refresh-datasets
// Visual: chip filter bar + folder tree + sub-folder by dataset_type + DatasetRow
// States: default / hover / loading / error / empty (per §7)
```

### `<DatasetRow>`
```ts
export let dataset: DatasetMeta;
export let groupColor: string;
export let selected: boolean;
// Events: select
// Visual: <DatasetIcon> + name + row_count(mono) + updated_at(mono)
```

### `<DatasetIcon>`
```ts
export let datasetType: string;        // csv / sqlite / json / parquet / xlsx / arrow
export let size: 'sm' | 'md' = 'md';   // sm: 24×30, md: 36×44
// Color: var(--ds-{type})
```

### `<Resizer>`
```ts
export let side: 'left' | 'right';
export let onResize: (newClientX: number) => void;
// Behavior: 7px hit zone + 2px visual bar (hover/drag opacity 0.5)
// Implements: mousedown → window mousemove/mouseup, body cursor + userSelect override
```

### `<CanvasFeed>`
```ts
export let messages: ChatMessage[];
export let isStreaming: boolean;
// Derived: canvasCards (見 §4.3)
// Auto-scroll: 200px threshold + "↓ 有新圖表" floating button
// Listens: workspaceEvents.focusCanvasCard → scrollIntoView + highlight 1.5s
```

### `<ChartCardCanvas>`
```ts
export let card: CanvasCard;
export let highlighted: boolean = false;
// Renders: header (title + chart_type badge + timestamp)
//        + image (with on:error fallback)
//        + caption block (explanation: source/method/fields/aggregation/notes/statistics)
//        + footer (message_id, debug only)
```

### `<ChatPlaceholder>` (注入到 native ResponseMessage)
```ts
export let attachmentId: string;
export let title: string;
export let chartType: string;
// Click: workspaceEvents.emit('focusCanvasCard', { attachmentId })
```

### Right panel: `<Chat>` (Open WebUI native)
```svelte
<Chat
    bind:chatId
    bind:history
    tool_ids={['builtin:data-analysis']}
    metadata={{
        workspace_type: 'data-analysis',
        selected_dataset_id: $selectedDatasetIdStore,
        version: 1
    }}
/>
```
Plan A/B/C decision per inventory（見 §9 in teaching）。

---

## 3. Stores

### Reuse 原生（不複製）
- `chats`、`models`、`user`、`config`、`showSidebar`、`history`、`colorScheme`

### Vertical-only stores
```ts
// src/lib/stores/data-analysis.ts
export const selectedDatasetId = writable<string>('');
export const datasets = writable<DatasetMeta[] | null>(null);
export const datasetsState = writable<{
    loading: boolean;
    error: string | null;
    lastFetched: number;
}>({ loading: false, error: null, lastFetched: 0 });

// Cross-component pub/sub (ephemeral, no persist)
export const workspaceEvents: {
    on(event: string, fn: (p: any) => void): () => void;
    emit(event: string, payload: any): void;
};
```

### Per-chat state
- Live in `chat.chat.metadata.data_analysis.*`
- `selectedDatasetId` store 是 mirror，從目前 chat metadata sync
- 切 chat → 重新 sync from new chat metadata
- User 改 dataset → 1) update store 2) `updateChatById(...)`

### Canvas state
- 永遠 derived，**不存**
- Scroll position / collapse / highlighted card id：local component state

---

## 4. Event Flow

### 4.1 Dataset 切換
```
DatasetPanel dispatch('select-dataset', { datasetId })
  → +page handler:
      selectedDatasetId.set(datasetId)
      updateChatById(chatId, { ...metadata, data_analysis: { ...selected_dataset_id } })
```

### 4.2 Placeholder → Canvas focus
```
User clicks "定位" in chat (rendered by injected <ChatPlaceholder>)
  → workspaceEvents.emit('focusCanvasCard', { attachmentId })
  → CanvasFeed listener:
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setHighlight(attachmentId, 1500ms)
```

### 4.3 New chart streamed
```
Native Chat updates history.messages[].toolCalls[]
  → CanvasFeed reactive:
      $: canvasCards = messages
          .flatMap(m => (m.toolCalls ?? [])
              .filter(tc => tc.function?.name === 'render_chart' &&
                            tc.result?.type === 'image' &&
                            tc.result?.attachment?.id)
              .map(tc => ({ ...tc.result.attachment, messageId: m.id, toolCallId: tc.id })))
  → afterUpdate hook:
      if (isNearBottom() || forceScrollOnSubmit) scrollToBottom()
      else showNewChartButton = true
```

### 4.4 Streaming 完成 → 持久化
- 原生機制自動 `updateChatById`，vertical 不做事

---

## 5. Auto-scroll Rules

| 區域 | 來源 | 規則 |
|---|---|---|
| Chat | 原生 `Messages.svelte` | 完全使用原生 |
| Canvas | Vertical 自製 | 與原生規則一致：200px threshold + "↓ 有新圖表" 浮動按鈕 |

### Canvas trigger 表
| 觸發 | 條件 | 行為 |
|---|---|---|
| 新 card | `isNearBottom(200)` | smooth scroll to bottom |
| 新 card | 偏離 > 200px | 不 scroll，show button |
| User submit | always | force scroll to bottom |
| Click button | always | smooth scroll, hide button |
| Click placeholder | always | scroll + highlight 1500ms |
| Streaming update | `isNearBottom` | stick-to-bottom |

```ts
// scroll-utils.ts
export const isNearBottom = (el, threshold = 200) =>
    el.scrollHeight - (el.scrollTop + el.clientHeight) <= threshold;

export const scrollToBottom = (el, behavior = 'smooth') =>
    el.scrollTo({ top: el.scrollHeight, behavior });
```

---

## 6. Native Chat Extension (Placeholder Render)

### Path FE-A/B/C decision
依 [`inventory-results.md`](./inventory-results.md) 選一：
- **FE-A**: 原生支援 `attachment.metadata.render_mode = 'placeholder'`
- **FE-B**: wrap / context cascade
- **FE-C**: CSS hide + DOM mutation observer inject（`[core-touch]` 規避）

### `<ChatPlaceholder>` 注入機制
不論 A/B/C，最終效果是 chat 內 chart attachment 渲染為小卡片（不顯示完整大圖），點按鈕觸發 `workspaceEvents.focusCanvasCard`。

---

## 7. State Matrix

| 元件 | default | hover | selected | focus | disabled | loading | empty | error |
|---|---|---|---|---|---|---|---|---|
| DatasetRow | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| DatasetPanel | ✓ | — | — | — | — | ✓ skeleton | ✓ "No datasets" | ✓ red banner + retry |
| ChartCardCanvas | ✓ | — | — | — | — | ✓ image loading | — | ✓ image error fallback |
| CanvasFeed | ✓ | — | — | — | — | ✓ first chart | ✓ "Ask for chart" | — |
| ChatPlaceholder | ✓ | ✓ | — | ✓ | — | — | — | — |

---

## 8. Persistence (Reload Round-Trip)

### Enter `/workspace/data-analysis/{chatId}`
1. `getChatById(chatId)` → fetch chat document
2. Validate `metadata.workspace_type === 'data-analysis'`，否則 `goto('/c/' + chatId)`
3. Set `selectedDatasetId` from `metadata.data_analysis.selected_dataset_id`
4. Pass `chat.chat.history` 給 native `<Chat>`
5. CanvasFeed reactive `canvasCards` 自動還原
6. ChartCardCanvas 的 `<img>` URL 指向 `/api/v1/data-analysis/charts/{id}.png`
7. Cache miss → backend 自動 regen（~3s 首張延遲）

### Enter `/workspace/data-analysis` (no chat id)
- 顯示歡迎頁 + dataset picker + suggestion prompts
- 不自動建 chat，user 送第一句才建

---

## 9. Native Chat Integration Plan A/B/C

| Plan | Trigger | Effort |
|---|---|---|
| **A**（首選）| 原生 `<Chat>` 接受 `tool_ids` + `metadata` props | 0 core touch |
| **B** | service worker / fetch interceptor patches outgoing chat completion request | medium |
| **C**（最後手段）| `[core-touch]` 加 `extraToolIds` / `extraMetadata` props 到 `<Chat>` | low (1 commit) |

Day 1 inventory 必決定。

---

## 10. i18n / a11y

- 所有 user-facing 字串走 `$i18n.t('data_analysis.xxx')`
- Locale: `src/lib/i18n/locales/{lang}/translation.json` 加 `data_analysis` namespace
- `aria-label` 所有 button、`alt` 所有 `<img>`
- Skeleton: `aria-busy="true"`
- Modal: focus trap + ESC close
- Tab order: left → middle → right
- Lighthouse a11y ≥ 90

---

## 11. Custom Files Cap

| File | Lines | Mockup |
|---|---|---|
| `+page.svelte` | ~200 | — |
| `[id]/+page.svelte` | ~250 | App (821-886) |
| `DataAnalysisLayout.svelte` | ~80 | App flex |
| `DatasetPanel.svelte` | ~280 | LeftPanel (156-358) |
| `DatasetRow.svelte` | ~80 | FileRow (367-399) |
| `DatasetIcon.svelte` | ~30 | FileIcon (96-112) |
| `Resizer.svelte` | ~60 | Resizer (115-155) |
| `CanvasFeed.svelte` | ~200 | MiddlePanel + ContentViewer |
| `ChartCardCanvas.svelte` | ~180 | adapted ContentViewer body |
| `ChatPlaceholder.svelte` | ~70 | — |
| `scroll-utils.ts` | ~30 | — |
| `data-analysis.ts` (store) | ~80 | — |
| `data-analysis/index.ts` (api) | ~60 | — |
| `data-analysis-tokens.css` | ~80 | from design-tokens |
| `data_analysis.json` (i18n) | n/a | — |

**Hard cap: 15 files, ~1680 LOC**.

---

## 12. Definition of Done

- [ ] All Tier 3 files in §11 list, no additions
- [ ] No custom MessageThread / streaming reducer / SSE parser
- [ ] No `import httpx` in frontend
- [ ] All cross-component communication via `dispatch` or `workspaceEvents`，prop drilling ≤ 3 levels
- [ ] All user-facing strings i18n
- [ ] Keyboard navigable (Tab + Enter)
- [ ] Reload chat → canvas fully restored
- [ ] Lighthouse a11y ≥ 90
- [ ] ≥ 5 vitest tests: DatasetPanel, CanvasFeed (auto-scroll), ChartCardCanvas (image fallback), ChatPlaceholder, scroll-utils

---

## 13. Anti-pattern Quick List

- 自寫 MessageThread → use native `<Chat>`
- 自寫 streaming reducer → native handles it
- vertical state outside `chat.chat.metadata` → wrong
- Canvas 維護 `cards: Card[]` → derived
- Sidebar 加全域 store 紀錄 vertical → 用 `$page.url.pathname`
- `<img>` no `on:error` fallback → must have
- Hard-code chart_type strings → import const
- Polling for new chart → reactive history

---

## 跨檔關聯

- 視覺 token：[`frontend-design-tokens.brief.md`](./frontend-design-tokens.brief.md)
- Tool 機制：[`tools-schema.brief.md`](./tools-schema.brief.md)
- Domain UX：[`data-analysis-vertical-spec.brief.md`](./data-analysis-vertical-spec.brief.md)
- 模組可重用清單：[`openwebui-module-inventory.brief.md`](./openwebui-module-inventory.brief.md)
- Day 1 決策：[`inventory-results.md`](./inventory-results.md)
