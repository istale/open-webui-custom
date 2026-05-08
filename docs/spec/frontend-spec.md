# Frontend Spec — Data Analysis Vertical Workspace

> **目的**：把前端從「3 個 Svelte 檔名」展開成可實作的契約。Code agent 在 Day 6 寫 UI 之前必讀。
>
> **依賴**：
> - [openwebui-module-inventory.md](./openwebui-module-inventory.md)（Tier 1 reuse）
> - [tools-schema.md](./tools-schema.md)（tool calling 機制）
> - [data-analysis-vertical-spec.md](./data-analysis-vertical-spec.md)（domain UX）
> - [inventory-results.md](./inventory-results.md)（Day 1 確認過的原生 props）
>
> **凍結原則**：這份規格鎖定**契約**（component props / event names / store shape / event flow）。不鎖實作（CSS、具體 layout DOM 結構可變）。

---

## 1. Routing & Entry Point

### 1.1 路由
- 路徑：`/workspace/data-analysis` 或 `/workspace/data-analysis/{chatId}`
- 檔案：`src/routes/(app)/workspace/data-analysis/+page.svelte`（無 chat）與 `src/routes/(app)/workspace/data-analysis/[id]/+page.svelte`（有指定 chat）
- **決策依據 inventory Day 1**：
  - 若原生 sidebar 支援 dynamic 註冊 → 透過該機制掛入口
  - 若是 hard-code → `[core-touch] Sidebar.svelte` 加 1 個 entry，commit 訊息明確標示

### 1.2 Sidebar 整合
- 加一個固定 entry 「Data Analysis」連到 `/workspace/data-analysis`
- 在 chat list 區段，**篩選**顯示：只有 `chat.chat.metadata.workspace_type === 'data-analysis'` 的 chat 顯示在這個 vertical 的 chat list 區（其他 chat 不顯示）
- Generic chats 不顯示在 vertical 區，反之 vertical chats 不污染 generic 區

### 1.3 New chat 行為
- 點「New analysis」按鈕 → 立刻建立一個新 chat：
  ```ts
  await createNewChat({
      models: [defaultModelId],
      metadata: {
          workspace_type: 'data-analysis',
          version: 1,
          data_analysis: {
              selected_dataset_id: defaultDatasetId,
              created_at: now()
          }
      }
  });
  ```
- 跳轉到 `/workspace/data-analysis/{newChatId}`

---

## 2. Layout 結構

```
+page.svelte (新建 chat 或 chat-id 頁面)
├── <DataAnalysisLayout>            # 三 panel grid
│   ├── slot="left"
│   │   └── <DatasetPanel>          # 共用 store 取目前 dataset
│   ├── slot="middle"
│   │   └── <CanvasFeed>            # derived from current chat history
│   └── slot="right"
│       └── <Chat>                  # ⚠️ 原生 Open WebUI Chat.svelte，不 fork
└── (responsive: <768px collapse 成 tab 切換)
```

### 2.1 `<DataAnalysisLayout>` (Tier 3 custom)
- **Path**：`src/lib/components/data-analysis/DataAnalysisLayout.svelte`
- **Props**：無
- **Slots**：`left`、`middle`、`right`
- **Behavior**：
  - Desktop：CSS grid `grid-template-columns: 320px 1fr 480px`
  - Tablet (<1280px)：`280px 1fr 400px`
  - Mobile (<768px)：tab bar 切換（Dataset / Canvas / Chat），預設 Chat
- **無 state**

### 2.2 `<DatasetPanel>` (Tier 3 custom)
- **Path**：`src/lib/components/data-analysis/DatasetPanel.svelte`
- **Props**：
  ```ts
  export let chatId: string | null;        // 用來 update chat metadata
  export let selectedDatasetId: string;
  export let datasets: DatasetMeta[];
  ```
- **Events**：
  ```ts
  dispatch('select-dataset', { datasetId: string })
  dispatch('refresh-datasets')
  ```
- **內容**：
  - Group filter（製造業：line / area / shift）
  - 搜尋框
  - Dataset list（virtualized 若 >100）
  - 已選 dataset 的 metadata 區（rows / columns / schema / tags / updated_at）
- **Loading state**：`datasets === null` → skeleton 3 row
- **Error state**：`datasetError != null` → red banner 含 retry button → emit `refresh-datasets`
- **Empty state**：no datasets accessible → "No datasets available. Contact admin."

### 2.3 `<CanvasFeed>` (Tier 3 custom)
- **Path**：`src/lib/components/data-analysis/CanvasFeed.svelte`
- **Props**：
  ```ts
  export let messages: ChatMessage[];      // 來自 native Chat 的 history
  export let isStreaming: boolean;          // 影響 loading state
  ```
- **Derived**：
  ```ts
  $: canvasCards = messages
      .flatMap((m) => (m.toolCalls ?? [])
          .filter((tc) =>
              tc.function?.name === 'render_chart' &&
              tc.result?.type === 'image' &&
              tc.result?.attachment?.id
          )
          .map((tc) => ({
              ...tc.result.attachment,
              messageId: m.id,
              toolCallId: tc.id,
              createdAt: m.timestamp ?? Date.now()
          }))
      );
  ```
- **無獨立 state**（除了 ephemeral scroll position）
- **Auto-scroll 行為**（與 chat 一致，下方 §5 有完整規則）
- **Empty state**：`canvasCards.length === 0 && !isStreaming` → "Ask the assistant for a chart to start the analysis canvas."
- **Loading state**：`isStreaming === true && canvasCards.length === 0` → spinner with "Generating first chart..."
- **Listens**：`workspaceEvents.focusCanvasCard` event → scroll to that card + highlight 1.5s

### 2.4 `<ChartCardCanvas>` (Tier 3 custom)
- **Path**：`src/lib/components/data-analysis/ChartCardCanvas.svelte`
- **Props**：
  ```ts
  export let card: CanvasCard;             // 包含 attachment + messageId + toolCallId
  export let highlighted: boolean = false;
  ```
- **Renders**：
  - Header：title + chart_type badge + 時間戳
  - 主圖：`<img src={card.url} alt={card.metadata.title} loading="lazy" />`（如失敗顯示 fallback）
  - Caption block（explanation：source / method / fields / aggregation / notes / statistics）
  - Footer：`message_id` + `tool_call_id`（debug 用，admin / dev mode 才顯示）
- **Image error handling**：`<img on:error={handleImageError}>` → 嘗試一次 reload，再失敗顯示 "Image regeneration in progress..."（依靠 backend regen fallback）
- **Highlighted state**：1.5s CSS class（border glow + bg flash），由 prop 控制

### 2.5 右欄：原生 `<Chat>`
- **Path**：`src/lib/components/chat/Chat.svelte`（原生，**不 fork**）
- **如何嵌入**：
  ```svelte
  <Chat
      bind:chatId={currentChatId}
      bind:history
      tool_ids={['builtin:data-analysis']}
      metadata={{
          workspace_type: 'data-analysis',
          selected_dataset_id: $selectedDatasetIdStore,
          version: 1
      }}
      ... 其他必要 props (依 inventory Day 1 確認)
  />
  ```
- **Props 細節依 [`inventory-results.md`](./inventory-results.md) Day 1 確認結果填入**。如果 native `<Chat>` 不接受 `tool_ids` 或 `metadata` 作為 props，回到 §9 「Native Chat Integration Plan B」走 form data 注入路徑。

---

## 3. Stores（State Management）

### 3.1 Reuse 原生
- `chats`、`models`、`user`、`config`、`showSidebar`、`history`：**全部直接用原生**，不複製
- 原生 `chats` store 有 reactivity → vertical chat 變動會自動更新 sidebar

### 3.2 Vertical-only stores（最少化）

```ts
// src/lib/stores/data-analysis.ts

import { writable, derived } from 'svelte/store';

/** 當前選中 dataset id (per-chat scoped via metadata)。 */
export const selectedDatasetId = writable<string>('');

/** Datasets 列表（從 list_datasets tool 拿，cache 1 分鐘）。 */
export const datasets = writable<DatasetMeta[] | null>(null);

/** Datasets loading / error 狀態。 */
export const datasetsState = writable<{
    loading: boolean;
    error: string | null;
    lastFetched: number;
}>({ loading: false, error: null, lastFetched: 0 });

/** Workspace ephemeral events (cross-component pub/sub)。 */
import { createEventDispatcher } from 'svelte';
export const workspaceEvents = (() => {
    const handlers = new Map<string, Set<(payload: any) => void>>();
    return {
        on(event: string, fn: (p: any) => void) {
            if (!handlers.has(event)) handlers.set(event, new Set());
            handlers.get(event)!.add(fn);
            return () => handlers.get(event)!.delete(fn);
        },
        emit(event: string, payload: any) {
            handlers.get(event)?.forEach((fn) => fn(payload));
        }
    };
})();
```

### 3.3 Per-chat state 在 chat metadata
- `chat.chat.metadata.data_analysis.selected_dataset_id` ← single source of truth
- `selectedDatasetId` store 是 mirror，從目前 chat metadata 同步來
- 切 chat → store 重新 sync from new chat metadata
- User 改 dataset → 1) 更新 store 2) 寫回 `chat.chat.metadata` via `updateChatById`

### 3.4 Canvas state 是 derived，不要存
- Canvas cards 從 `history.messages[].toolCalls[]` derived（見 §2.3）
- Scroll position / collapse state / highlighted card id：local component state，**不 persist**

---

## 4. Event Flow（跨元件溝通）

### 4.1 Dataset 切換流程
```
User clicks dataset in DatasetPanel
  └─> dispatch('select-dataset', { datasetId })
      └─> +page.svelte handler:
          1. selectedDatasetId.set(datasetId)
          2. updateChatById(chatId, {
                 chat: { ...chat, metadata: { ...metadata,
                     data_analysis: { ...metadata.data_analysis,
                         selected_dataset_id: datasetId } } }
             })
          3. (Optional) emit('dataset-changed', ...) for analytics
```

### 4.2 Chart placeholder → Canvas focus 流程
```
User clicks "📊 定位" in chat (rendered by native ResponseMessage)
  ↑ 從 tool call result 的 attachment id 派生
  └─> 這個 button 由我們 inject — 詳見 §6 Native Chat Extension Hooks
      └─> workspaceEvents.emit('focusCanvasCard', { attachmentId })
          └─> CanvasFeed listener:
              1. 找到對應 ChartCardCanvas DOM
              2. scrollIntoView({ behavior: 'smooth', block: 'center' })
              3. setHighlight(attachmentId, 1500ms)
```

### 4.3 New chart streamed → Canvas auto-scroll
```
Native Chat updates history.messages[].toolCalls[]
  └─> CanvasFeed reactive: $: canvasCards = ...derive...
      └─> canvasCards.length 增加
          └─> afterUpdate hook:
              if (isNearBottom() || forceScrollOnSubmit):
                  scrollToBottom()
              else:
                  showNewChartButton = true
```

### 4.4 Streaming 完成 → 持久化
```
Native Chat completes message
  └─> 原生機制自動 updateChatById (history persist)
  └─> Vertical 不需要做任何事 — toolCalls 自動進 chat document
```

---

## 5. Auto-Scroll 詳細規則（Chat + Canvas 雙區一致）

### 5.1 Chat 區
- **完全使用原生** `Messages.svelte` 的 auto-scroll
- 規格依原生為準，不另外定義（但 inventory Day 1 應確認原生有 IME guard、stick-to-bottom）

### 5.2 Canvas 區（vertical 自製，模仿原生規則）
| 觸發 | 條件 | 行為 |
|---|---|---|
| 新 card 加入 | `isNearBottom(threshold=200)` | 自動 smooth scroll 到底 |
| 新 card 加入 | 偏離底部 >200px | 不 scroll，顯示「↓ 有新圖表」浮動按鈕 |
| User 送訊息 | always | `forceScrollOnSubmit = true`（user 自己送的 = 想看回應）|
| 點「↓ 有新圖表」 | always | smooth scroll 到底，按鈕隱藏 |
| 點 placeholder 跳轉 | always | smooth scroll + highlight 1500ms（無視 stick rules）|
| Streaming 期間（同一 card 內容更新）| `isNearBottom` | stick-to-bottom |

### 5.3 公用 helper
```ts
// src/lib/components/data-analysis/scroll-utils.ts

export const isNearBottom = (el: HTMLElement, threshold = 200): boolean =>
    el.scrollHeight - (el.scrollTop + el.clientHeight) <= threshold;

export const scrollToBottom = (el: HTMLElement, behavior: ScrollBehavior = 'smooth') => {
    el.scrollTo({ top: el.scrollHeight, behavior });
};
```

---

## 6. Native Chat Extension Hooks（Placeholder & Caption）

### 6.1 問題
原生 `<ResponseMessage>` 看到 `tool_calls.result.attachment.type === 'image'` 會自動 render 一張圖（依 [inventory-results.md] Day 1 確認的渲染路徑）。但我們希望在 chat 內顯示**小 placeholder**（「📊 已加到分析畫布」+ 定位 button），而非完整大圖（大圖在中間欄）。

### 6.2 Day 1 inventory 必須確認的兩條路徑

**Path-FE-A（首選）**：原生支援 `attachment.metadata.render_mode = 'placeholder'`
- 原生看到此 flag → render 我們指定的 component
- 從 inventory Day 1 確認原生是否支援
- 若支援 → tool function `render_chart` 回 `attachment.metadata.render_mode = 'placeholder-with-canvas-link'`
- 前端透過 native slot / customElement registry 注入 `<ChatPlaceholder>` 元件

**Path-FE-B（fallback）**：覆寫 `<ResponseMessage>` 內的 attachment renderer
- 若原生無 hook → 在 vertical layout 外層 wrap 一層，cascade 一個 context 給內部 message renderer
- 若原生 ResponseMessage hard-code 圖片渲染 → `[core-touch]` 加一行 conditional check（提請 user 同意）

**Path-FE-C（最 fallback）**：CSS hide + DOM inject
- CSS 把原生大圖隱藏
- 透過 mutation observer 在訊息渲染後 inject placeholder
- 醜但保證能 work，且 0 core touch

### 6.3 `<ChatPlaceholder>` 元件契約
- **Path**：`src/lib/components/data-analysis/ChatPlaceholder.svelte`
- **Props**：
  ```ts
  export let attachmentId: string;
  export let title: string;
  export let chartType: string;
  ```
- **Renders**：
  ```
  📊 已加到分析畫布
  [chart title] · [chart_type]
  [定位 button]
  ```
- **Click**：
  ```ts
  workspaceEvents.emit('focusCanvasCard', { attachmentId });
  ```

---

## 7. Loading / Error / Empty States 矩陣

| 區域 | State | Trigger | 顯示 |
|---|---|---|---|
| DatasetPanel | Loading | `datasets === null` 且初次 fetch | Skeleton (3 rows) |
| DatasetPanel | Error | fetch fail | Red banner + Retry button |
| DatasetPanel | Empty | fetch ok 但 array 空 | "No datasets available." |
| CanvasFeed | Empty (no chat) | `chatId === null` | "Start by selecting a dataset and asking a question." |
| CanvasFeed | Empty (chat exists, no charts) | `canvasCards.length === 0 && !isStreaming` | "Ask the assistant for a chart." |
| CanvasFeed | Streaming first | `isStreaming && canvasCards.length === 0` | Spinner + "Generating first chart..." |
| CanvasFeed | Streaming additional | `isStreaming && canvasCards.length > 0` | 既有 cards + 底部 inline spinner |
| ChartCardCanvas | Image loading | `<img>` not yet loaded | aspect-ratio placeholder（避免 CLS） |
| ChartCardCanvas | Image error | `<img on:error>` | "Image regeneration in progress..." 含 manual retry |
| Right Chat | (依原生) | — | 由原生處理 |
| Layout | Streaming any | `isStreaming === true` | 全頁不可關閉 chat（原生機制）|

---

## 8. Reload 行為（Persistence Round-Trip）

### 8.1 進入 `/workspace/data-analysis/{chatId}`
1. `getChatById(chatId)` → 拿到完整 chat document
2. 驗證 `chat.chat.metadata.workspace_type === 'data-analysis'`
   - 若否 → redirect to `/c/{chatId}`（這是 generic chat，不該在 vertical 路由）
3. 從 `chat.chat.metadata.data_analysis.selected_dataset_id` set `selectedDatasetId` store
4. 把 `chat.chat.history` 傳給原生 `<Chat>` 渲染
5. CanvasFeed reactive `$: canvasCards` 自動從 history.toolCalls derive 出所有歷史圖表
6. 每張 ChartCardCanvas 的 `<img src>` 指向 `/api/v1/data-analysis/charts/{id}.png`
   - 若 cache 還在 → 直接顯示
   - 若 cache miss → backend regen → 仍顯示（user 感受到 ~3s 延遲首張，後續正常）

### 8.2 進入 `/workspace/data-analysis`（無 chat id）
1. 顯示「歡迎」畫面 + dataset picker + suggestion prompts
2. 不自動建 chat — user 點 "New analysis" 或選 dataset 後送第一句才建

---

## 9. Native Chat Integration — Plan A / B Decision

### Plan A（首選，依 inventory Day 1 確認原生支援）
原生 `<Chat>` 接受 props：
```ts
tool_ids: string[]
metadata: object
```
直接傳即可。

### Plan B（若原生只接受 form data）
我們在 vertical layout 內攔截 chat completion 的 fetch：
- 用 service worker 或 fetch interceptor
- 對 `/api/v1/chat/completions` 自動 patch `tool_ids` + `metadata`
- **複雜度高，避免使用，僅在 Plan A 不可行時走**

### Plan C（最後手段，[core-touch]）
原生 `<Chat>` 加 2 個 props：
```diff
- export let chatId;
+ export let chatId;
+ export let extraToolIds = [];
+ export let extraMetadata = {};
```
1 個 commit，標 `[core-touch]`，merge upstream 時優先檢查。

**Day 1 inventory MUST 決定哪個 plan**。

---

## 10. i18n / a11y / Responsive

### 10.1 i18n
- 所有 user-facing 字串走 `$i18n.t('data_analysis.xxx')`
- Locale files：`src/lib/i18n/locales/{lang}/translation.json` 加 `data_analysis` namespace
- Day 6 寫 UI 時順便加，不要事後補

### 10.2 Accessibility
- 所有 button 有 `aria-label`
- 圖表 `<img alt={title + chart_type}>`
- Skeleton loaders 用 `aria-busy="true"`
- Modal / overlay 有 focus trap + ESC close
- 鍵盤導覽：Tab 順序 left → middle → right

### 10.3 Responsive
| Width | Layout |
|---|---|
| ≥ 1280px | 三 panel grid |
| 768–1279px | 三 panel grid，左右欄縮窄 |
| < 768px | Tab bar 切換（Dataset / Canvas / Chat），預設 Chat |

---

## 11. Frontend Custom 檔案清單（Tier 3）

| 檔案 | 必要性 | 預估行數 |
|---|---|---|
| `src/routes/(app)/workspace/data-analysis/+page.svelte` | P0 | ~200 |
| `src/routes/(app)/workspace/data-analysis/[id]/+page.svelte` | P0 | ~250 |
| `src/lib/components/data-analysis/DataAnalysisLayout.svelte` | P0 | ~80 |
| `src/lib/components/data-analysis/DatasetPanel.svelte` | P0 | ~250 |
| `src/lib/components/data-analysis/CanvasFeed.svelte` | P0 | ~200 |
| `src/lib/components/data-analysis/ChartCardCanvas.svelte` | P0 | ~180 |
| `src/lib/components/data-analysis/ChatPlaceholder.svelte` | P0 | ~70 |
| `src/lib/components/data-analysis/scroll-utils.ts` | P0 | ~30 |
| `src/lib/stores/data-analysis.ts` | P0 | ~80 |
| `src/lib/apis/data-analysis/index.ts` | P0 | ~60（只 wrap 必要 endpoint）|
| `src/lib/i18n/locales/{lang}/data_analysis.json` | P1 | n/a |

**合計：~1400 行**，10 個前端檔案。比上次（~3000 行 + 6 個檔案不含 +page.svelte 的 2700 行）**少約 60%**，因為 reuse-first。

---

## 12. Definition of Done（Frontend）

- [ ] 所有 Tier 3 檔案在 §11 清單內，無新增
- [ ] 無自定 Message thread / 無自定 streaming reducer / 無自定 SSE 解析
- [ ] 無 `import httpx`（前端不該 import 後端 lib，這條 sanity check）
- [ ] 所有跨元件 communication 走 `dispatch` 或 `workspaceEvents`，無 prop drilling >3 層
- [ ] 所有 user-facing 字串 i18n
- [ ] 全 keyboard 可操作（Tab + Enter）
- [ ] Reload chat 後 canvas 完整還原
- [ ] Mobile (<768px) layout 可用
- [ ] Lighthouse a11y score ≥ 90
- [ ] 至少 5 個 vitest 元件 test：`DatasetPanel`、`CanvasFeed` (auto-scroll)、`ChartCardCanvas` (image fallback)、`ChatPlaceholder`、scroll-utils

---

## 13. Anti-patterns (前端版)

| 反 pattern | 正解 |
|---|---|
| 自寫 `MessageThread.svelte` | 用原生 `<Chat>` |
| 自寫 streaming reducer | 原生處理 |
| 從 `chat.chat` 以外的地方持久化 vertical state | 一律進 `chat.chat.metadata` |
| Canvas 維護獨立 `cards: Card[]` | 永遠 derived from `history.messages[].toolCalls[]` |
| Sidebar 加全域 store 紀錄目前 vertical | 用 `$page.url.pathname` 判斷 |
| `<img>` 失敗就 crash | `on:error` fallback + retry |
| 前端硬寫 chart_type 字串 | 從 spec 引入 const |
| Polling 來偵測新 chart | 原生 history reactivity 自動處理 |
