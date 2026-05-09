# Frontend Spec — Data Analysis Vertical Workspace

> **目的**：把前端從「3 個 Svelte 檔名」展開成可實作的契約。Code agent 在 Day 6 寫 UI 之前必讀。
>
> **依賴**：
> - [openwebui-module-inventory.md](./openwebui-module-inventory.md)（Tier 1 reuse）
> - [tools-schema.md](./tools-schema.md)（tool calling 機制）
> - [data-analysis-vertical-spec.md](./data-analysis-vertical-spec.md)（domain UX）
> - [frontend-design-tokens.md](./frontend-design-tokens.md)（**視覺 design system，色彩 / 字體 / 互動 pattern**）
> - [inventory-results.md](./inventory-results.md)（Day 1 確認過的原生 props）
> - [docs/design/mockup-analysis.md](../design/mockup-analysis.md)（user-designed mockup 對應分析）
>
> **凍結原則**：這份規格鎖定**契約**（component props / event names / store shape / event flow）。**視覺 token / 互動 pattern 由 [frontend-design-tokens.md](./frontend-design-tokens.md) 定義**，本檔不重複。
>
> **預設情境**：使用者在 desktop browser 全螢幕使用，不另做 responsive（依 user 確認 2026-05-09）。

---

## 1. Routing & Navigation Flow

> **誰需要讀**：Frontend dev、Backend dev、PM、Designer。**這節是團隊共識基礎**，看完才能理解後面所有 spec 為什麼這樣寫。
>
> **預設讀者程度**：第一次碰 SvelteKit / 第一次碰 Open WebUI。每個概念都會說清楚「是什麼 / 為什麼這樣 / 怎麼做」。

---

### 1.1 概念基礎（必讀）

#### 1.1.1 什麼是 SvelteKit Routing
SvelteKit 用**檔案路徑**對應 URL：

| 檔案 | URL |
|---|---|
| `src/routes/+page.svelte` | `/` |
| `src/routes/c/[id]/+page.svelte` | `/c/abc123`（`[id]` 是動態參數）|
| `src/routes/workspace/data-analysis/+page.svelte` | `/workspace/data-analysis` |
| `src/routes/workspace/data-analysis/[id]/+page.svelte` | `/workspace/data-analysis/abc123` |

**規則**：
- `+page.svelte` = 該 URL 的主要內容
- `+layout.svelte` = 包覆 `+page.svelte` 的外層（可巢狀）
- `[name]` = 動態 segment（在 `$page.params.name` 拿到值）
- `(group)` = 路由群組，**不影響 URL**，只用來分享同一個 layout（例如 `(app)/...` 跟 `(auth)/...` 各有自己的 layout 但 URL 不會多 `/app`）

> 第一次接觸 SvelteKit 的隊員，建議先看 [SvelteKit Routing Docs (10 分鐘)](https://kit.svelte.dev/docs/routing) 再回來讀。

#### 1.1.2 什麼是 Nested Layout
SvelteKit 的 `+layout.svelte` 會自動把 `+page.svelte` 嵌進它的 `<slot />`。**多層 layout 會層層包覆**。

範例：
```
src/routes/
├── +layout.svelte             ← 最外層（含 sidebar）
└── (app)/
    ├── +layout.svelte         ← app 內共用（含 navbar）
    └── workspace/
        └── data-analysis/
            ├── +layout.svelte     ← 三欄版型 wrap
            └── [id]/+page.svelte  ← 真正的頁面
```

當 user 訪問 `/workspace/data-analysis/abc123`，瀏覽器最終看到：

```
<最外層 layout>
  <sidebar/>
  <slot>                            ← 嵌入 app layout
    <app layout>
      <navbar/>
      <slot>                        ← 嵌入 vertical layout
        <vertical 三欄 layout>
          <DatasetPanel/>
          <CanvasFeed/>
          <Chat/>
          <slot>                    ← 嵌入 page
            <[id]/+page.svelte>
          </slot>
        </vertical>
      </slot>
    </app>
  </slot>
</最外層>
```

**關鍵**：當 URL 切到別的路由（例如 `/c/xyz`），vertical layout 自動消失，三欄畫面不見，主內容變成原生 chat。Sidebar / app layout 不變。

> **這就是「URL 換版型」的機制**：根本不是寫 `if isVertical { showThreePanel }`，是路徑檔案存在與否決定 layout 包不包。

#### 1.1.3 URL 是 single source of truth
不要用全域 store 記「現在是 vertical 模式」。**永遠靠 URL 判斷**。理由：
- 複製 URL 給同事，他打開就是同一畫面
- 重整頁面，狀態不會掉
- Browser 上一頁 / 下一頁自然 work
- 0 全域 state 同步 bug

判斷方式：
```ts
import { page } from '$app/stores';
$: isVertical = $page.url.pathname.startsWith('/workspace/data-analysis');
```

#### 1.1.4 Open WebUI App Shell
Open WebUI 自己的 layout 大致長這樣（Day 1 inventory 確認細節）：

```
<+layout.svelte>             ← Open WebUI root
  <Sidebar />                ← 左側 chat list + folder + new chat
  <main>
    <slot />                 ← 路由的內容嵌這
  </main>
</+layout.svelte>
```

我們的 vertical workspace **不取代這個 shell**，是嵌進 `<slot />` 的內容。**Sidebar 永遠在**，無論 user 在 native chat 還是 vertical。

---

### 1.2 Navigation Map（一張圖看懂）

```
                     ┌───────────────────────────────┐
                     │ Open WebUI                    │
                     │  Sidebar 永遠在                │
                     │  ┌───┬───┬───────┐           │
                     │  │ + │📊 │ chats │           │
                     │  └───┴───┴───────┘           │
                     │                               │
                     │  主內容區依 URL 換版型 ↓        │
                     └───────────────────────────────┘

URL                                    主內容區
─────────────────────────────────────  ─────────────────────────
/                                       Open WebUI 首頁
/c/{chatId}                             Native chat 介面
/workspace/data-analysis                三欄（無 chat，歡迎頁）
/workspace/data-analysis/{chatId}       三欄（含 active chat）
/admin/...                              Open WebUI admin（不變）
```

| URL Pattern | Layout | 何時看到 |
|---|---|---|
| `/` | Open WebUI native | 開 app 預設 |
| `/c/{id}` | Open WebUI native chat | 點 sidebar 內 generic chat |
| `/workspace/data-analysis` | **三欄（vertical 歡迎頁）** | 點 sidebar 「📊 Data Analysis」入口 |
| `/workspace/data-analysis/{id}` | **三欄（vertical with chat）** | 在 vertical 內送訊息建 chat、或點 sidebar 內 vertical chat |

---

### 1.3 SvelteKit 檔案結構（具體）

依 Day 1 inventory 結果（路由群組 `(app)` 是否存在），最終 path 可能微調。預設長這樣：

```
src/routes/
├── +layout.svelte                      ← Open WebUI 自帶，不動
├── +page.svelte                        ← Open WebUI 首頁，不動
│
├── c/[id]/+page.svelte                 ← Open WebUI generic chat，不動
│
└── (app)/                              ← Open WebUI 既有 group（如有）
    └── workspace/
        └── data-analysis/
            ├── +layout.svelte          ← 三欄 wrap (DataAnalysisLayout)
            ├── +page.svelte            ← /workspace/data-analysis (歡迎/新分析頁)
            └── [id]/
                └── +page.svelte        ← /workspace/data-analysis/{id}
```

**每個檔案的職責**：

| 檔案 | 內容 |
|---|---|
| `(app)/workspace/data-analysis/+layout.svelte` | 包 `<DataAnalysisLayout left middle right>`、訂閱 `chats` store 取出當前 vertical chat、初始化 `selectedDatasetId` store、Resizer 寬度 localStorage 還原 |
| `(app)/workspace/data-analysis/+page.svelte` | 「歡迎/新分析頁」：左欄 dataset picker；中欄空狀態 placeholder；右欄空狀態（"Type to start a new analysis…"）。**沒有 active chatId**。送第一句訊息時：(1) 建 vertical chat (2) `goto('/workspace/data-analysis/' + newChatId, { replaceState: true })` |
| `(app)/workspace/data-analysis/[id]/+page.svelte` | 「進行中分析頁」：load chat by id、驗證 `metadata.workspace_type === 'data-analysis'`、傳給 layout 三欄渲染、右欄是 native `<Chat>` |

> **Layout vs Page 的分工**：layout 放跨頁面共用結構（三欄、sidebar trigger），page 放具體內容（active chat 或歡迎頁）。`/workspace/data-analysis` 跟 `/workspace/data-analysis/{id}` **共用同一 layout**，只有中欄 / 右欄內容不同 — 這就是 layout 的價值。

---

### 1.4 Sidebar Entry — 怎麼加「📊 Data Analysis」入口

這是 Day 1 inventory **必須回答**的問題（已記在 [`inventory-results.md`](./inventory-results.md)）。三種可能：

#### Plan A — Open WebUI sidebar 支援 dynamic entry registration（最理想）

**判斷依據**：grep `Sidebar.svelte` 找到類似 `registerSidebarEntry()` / `sidebarItems` 配置 store / plugin hook。

**做法**：
```ts
// 在 +layout.svelte 或 app initialization
import { registerSidebarEntry } from '$lib/sidebar';

registerSidebarEntry({
    id: 'data-analysis',
    label: 'Data Analysis',
    icon: '📊',  // 或 inline SVG
    href: '/workspace/data-analysis',
    section: 'workspaces'  // 看原生分組策略
});
```

**0 動 Sidebar.svelte，0 衝突**。

#### Plan B — Sidebar 是 hard-coded 但有可擴展點（lookup config）

**判斷依據**：Sidebar.svelte 內看到 `import { sidebarItems } from '...'` 之類的設定檔。

**做法**：在那個 config 檔加一筆，或 monkey-patch。`[core-touch]` 但只動 config 不動 component。

#### Plan C — Sidebar 完全 hard-coded（最常見的最壞情況）

**做法**：直接修改 `src/lib/components/layout/Sidebar.svelte`，加 1 個 NavItem。

```svelte
<!-- 在原生 sidebar 適當位置 -->
<a
    href="/workspace/data-analysis"
    class="sidebar-item {$page.url.pathname.startsWith('/workspace/data-analysis') ? 'active' : ''}"
>
    <span class="icon">📊</span>
    <span class="label">{$i18n.t('Data Analysis')}</span>
</a>
```

- Commit 訊息加 `[core-touch]` 前綴
- 升 upstream 時這幾行可能要重做 conflict resolution

> **無論哪個 Plan，做法都應該寫進 `inventory-results.md`**，PR 時附引用。

---

### 1.5 進入 Vertical Workspace 的三條路徑

```
路徑 1: 開新分析（從非 vertical 任何地方）
  Sidebar 點「📊 Data Analysis」
    → URL: /workspace/data-analysis
    → 看到三欄（中右欄空狀態）

路徑 2: 進入既有 vertical chat（從 sidebar list）
  Sidebar 點某個帶 📊 icon 的 chat
    → URL: /workspace/data-analysis/{chatId}
    → 看到三欄（已有對話 + 既有 chart）

路徑 3: 從歡迎頁送第一句訊息
  在 /workspace/data-analysis 頁面
  選 dataset → 輸入問題 → 送出
    → 後端建立 chat
    → goto('/workspace/data-analysis/' + newId)
    → URL 變更，沿用同一 layout（不重渲染）
    → Active chat 進入流式渲染
```

**三條都最終匯流到 `/workspace/data-analysis/{id}`**，三欄畫面渲染。

---

### 1.6 「+ New Chat」按鈕行為對照

| 按鈕位置 | 點擊後行為 | 建立的 chat 類型 |
|---|---|---|
| Sidebar 的「+ New Chat」（原生） | URL → `/`，新 generic chat | generic |
| Sidebar 的「📊 Data Analysis」（我們加的）| URL → `/workspace/data-analysis`（**不是直接建 chat**） | — |
| Vertical 歡迎頁的「New Analysis」/送第一句 | 建 vertical chat、URL → `/workspace/data-analysis/{id}` | **vertical**（`metadata.workspace_type='data-analysis'`）|

> 為什麼 sidebar 的「📊 Data Analysis」**不直接建 chat**？因為 user 還沒選 dataset / model。先進歡迎頁讓他挑，避免造成「點一下產生空 chat」的垃圾資料。

---

### 1.7 Vertical Chat vs Generic Chat 在 Sidebar 怎麼分

**核心 discriminator**：`chat.chat.metadata.workspace_type`
- `'data-analysis'` → vertical chat
- `undefined` 或其他值 → generic chat

**視覺區分方式**（依 inventory 後決定）：

| 方案 | 描述 | 適用 |
|---|---|---|
| **A. Icon 前綴** | sidebar list item 開頭加 📊 | 最低成本，視覺立刻可辨 |
| **B. 自動歸入 system folder** | 新建 vertical chat 時自動 `chat.folder_id = 'data-analysis-folder-id'` | 想要群組收合 |
| **C. Badge 在右側** | item 右側貼 `D-A` badge | 中性，不搶 title |
| **D. 完全不分** | 混著看，靠 chat title 自己分辨 | 最低工時 |

**目前傾向 A + B 組合**，但等 inventory 確認 sidebar 是否能加 icon 與 folder 機制是否能用後決定。

**Click 行為**：
```ts
// Sidebar list item click handler 必須：
const handleChatClick = (chat) => {
    const isVertical = chat?.chat?.metadata?.workspace_type === 'data-analysis';
    if (isVertical) {
        goto(`/workspace/data-analysis/${chat.id}`);
    } else {
        goto(`/c/${chat.id}`);  // 原生路徑
    }
};
```

> 這個 click handler 是**唯一需要動到 sidebar 的邏輯改動**（Plan C 情境）。Plan A/B 可能只要設定一筆 router rule 而已。

---

### 1.8 Step-by-step 使用者流程（從 0 到看到第一張圖）

新使用者第一次操作的完整路徑：

| Step | User 動作 | URL | 主內容變化 | 後台動作 |
|---|---|---|---|---|
| 1 | 開 app | `/` | Open WebUI 首頁 | — |
| 2 | 點 sidebar 的「📊 Data Analysis」 | `/workspace/data-analysis` | 三欄出現，中右欄空狀態 | layout mount、訂閱 stores |
| 3 | 看到左欄 dataset list（loading skeleton 1–2 秒）| 同上 | dataset 載入完成 | `list_datasets` tool 呼叫（**後端**）|
| 4 | 點選某個 dataset | 同上 | 左欄該 row selected、中欄仍空 | `selectedDatasetId` store 更新 |
| 5 | 在右欄輸入「show monthly trend」按 Enter | 同上 → `/workspace/data-analysis/{newId}` | URL 改變，layout 不重 mount | (1) `createNewChat` API 建 vertical chat<br>(2) 寫入 metadata `{ workspace_type, selected_dataset_id }`<br>(3) `goto(...)` URL 改 |
| 6 | 看到右欄 user 訊息泡泡，下方 thinking 動畫 | 同上 | `<Chat>` 接管 streaming | 開始送 chat completion，model 生成 |
| 7 | Model 決定呼叫 `query_dataset` | 同上 | 右欄出現 tool call 「Executing…」 | Backend execute query、回傳 query_id + preview |
| 8 | Model 決定呼叫 `render_chart` | 同上 | 右欄 tool call 「Executing…」 | Backend matplotlib render PNG → 存 cache → 回傳 attachment |
| 9 | 中欄 canvas 出現第一張卡片（appear animation）+ 自動 scroll 到底 | 同上 | `canvasCards` reactive 增加 | image url fetch from `/api/v1/data-analysis/charts/{id}.png` |
| 10 | 右欄訊息渲染完成，顯示 placeholder「📊 已加到分析畫布 [定位]」 | 同上 | 文字內容流式完成 | message done=true、metadata 持久化 |
| 11 | 使用者點 placeholder 的「定位」 | 同上 | 中欄對應 card 被 scroll + 1.5s highlight | DOM scrollIntoView + class toggle |
| 12 | 使用者繼續輸入下一句「跟去年比」 | 同上 | 右欄新訊息 + 中欄追加新 card（自動 scroll）| 重複 6–10 |

每一格的「後台動作」對應 Day 4–5 backend tools 與 Day 6 frontend wiring 的具體任務。團隊在實作時可以對照這張表 review「我們做到第幾步」。

---

### 1.9 Step-by-step 工程師實作（Day 6 frontend）

依**順序執行**，每一步都要可獨立 demo：

#### Step 1 — 路由與 layout 骨架（0.5 day）
1. 新建 `src/lib/components/data-analysis/DataAnalysisLayout.svelte`
   - 純 layout：3 個 column + 兩個 `<Resizer>`
   - 暫時 props 為空，`<slot name="left">` `<slot name="middle">` `<slot name="right">`
2. 新建 `src/routes/(app)/workspace/data-analysis/+layout.svelte`
   - import 上面 layout
   - 三個 slot 暫時用 placeholder：`<div>Dataset Panel</div>` / `<div>Canvas</div>` / `<div>Chat</div>`
3. 新建 `+page.svelte` 與 `[id]/+page.svelte`，內容暫空
4. **Demo**：訪問 `/workspace/data-analysis` 看到三個區塊輪廓、Resizer 可拖

#### Step 2 — Sidebar entry（0.5 day）
1. inventory 確認的 Plan A/B/C 擇一執行
2. **Demo**：sidebar 新增「📊 Data Analysis」，點下去 URL 切到 `/workspace/data-analysis`

#### Step 3 — 接 native `<Chat>` 進右欄（0.5 day）
1. inventory 確認 `<Chat>` 的 props（`chatId`、`tool_ids`、`metadata` 等）
2. layout 右欄 slot 換成 `<Chat tool_ids={['builtin:data-analysis']} ... />`
3. **Demo**：訪問 `/workspace/data-analysis/{某個 vertical chat id}` 看到 native chat 渲染對話

#### Step 4 — DatasetPanel 串假資料（0.5 day）
1. 寫 `<DatasetPanel>`，用 mockup HTML 做為視覺參考
2. 用 hardcoded 假 dataset 列表先測 visual
3. **Demo**：左欄 chip filter / folder tree / dataset row 互動 OK

#### Step 5 — 接 `list_datasets` tool（0.25 day）
1. 假資料換成從 `list_datasets` API call
2. Loading / Error / Empty state 接齊
3. **Demo**：dataset list 從後端真實取得

#### Step 6 — CanvasFeed derived view（0.5 day）
1. 寫 `<CanvasFeed>`，subscribe `history.messages`
2. derived `canvasCards = ...flatMap(toolCalls).filter(render_chart)...`
3. 用「製作中 / 完成」假 chart（hard-coded `<img>` 或 placeholder）測渲染
4. **Demo**：手動 mock 一個 toolCall 看 canvas 出 card

#### Step 7 — Auto-scroll 行為（0.5 day）
1. Chat 區：依 `MessageThread` 規格實作（其實 native 已經有，看 inventory Day 1 確認是否需自己做）
2. Canvas 區：實作 200px 偏離規則 + 「↓ 有新圖表」按鈕
3. **Demo**：連送 3 張 chart 看 scroll 行為

#### Step 8 — Placeholder 與 scroll-to-canvas-card（0.5 day）
1. 寫 `<ChatPlaceholder>`
2. 透過 inventory 確認的 ResponseMessage hook 注入
3. 點 placeholder「定位」→ workspaceEvents emit → CanvasFeed listener → scrollIntoView + highlight
4. **Demo**：點 chat 內 placeholder 跳到對應 chart card

#### Step 9 — IME guard / Enter 送出（0.25 day）
1. Native `<MessageInput>` 應已處理（Day 1 inventory 確認）
2. 若沒處理 → 我們自己加（用 wrapper component 攔截 keydown）
3. **Demo**：中文輸入法選字按 Enter 不誤送

#### Step 10 — Persistence 驗證（0.25 day）
1. 送 3 張 chart → 重整頁面 → 三張都在
2. 切到 generic chat → 切回 vertical → 狀態還原
3. **Demo**：reload 頁面測試

每一步**完成才進下一步**。每步都對應 1–2 個 commit。

---

### 1.10 Anti-patterns（前端 routing 常見錯誤）

| 反 pattern | 為什麼錯 | 正解 |
|---|---|---|
| 用全域 store 記「現在 vertical mode」| Source of truth 錯 — URL 才是 | `$page.url.pathname` 判斷 |
| 在 layout `+layout.svelte` 內 `goto('/workspace/...')` 做重導 | 會無限迴圈 | 重導邏輯放 `+layout.ts` `load()` 或 `+page.ts` |
| Page-level 維護 `cards: Card[]` array | 雙來源 sync bug | 永遠 derived from message tree |
| 自己寫 SSE consumer 接 vertical 自定 events | 重做了 native 已有的事 | 走 native tool calling，事件包進 `toolCalls[]` |
| 在 vertical layout 裡 import `chats` store 並 mutate | 違反原生 store ownership | 用原生 API（`updateChatById`），讓原生 store 自己 reactive |
| Sidebar 點 vertical chat 卻跳 `/c/{id}` | 進到 generic chat 介面，使用者困惑 | sidebar handler 偵測 `metadata.workspace_type` 切路徑 |
| Hard-code 路徑字串 `'/workspace/data-analysis/'` 散布各處 | 改路徑時要改 N 處 | 集中在 `src/lib/utils/data-analysis-paths.ts` |
| 用 `window.location.href = '...'` 切頁 | 觸發整頁 reload，layout 重 mount | 用 `goto()` from `$app/navigation` |

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
- **Props**：
  ```ts
  export let leftWidth: number = 300;
  export let rightWidth: number = 480;
  ```
- **Slots**：`left`、`middle`、`right`
- **Layout**：3-column flex / grid
  - Left: `width: {leftWidth}px`
  - Middle: `flex: 1, min-width: 0`
  - Right: `width: {rightWidth}px`
- **Resizable**：
  - Left ↔ Middle 之間放 `<Resizer side="right" onResize={...}>` (200–560px clamp)
  - Middle ↔ Right 之間放 `<Resizer side="left" onResize={...}>` (320–640px clamp)
  - 寬度持久化：寫進 `localStorage` key `data-analysis.layout.{leftWidth,rightWidth}`，下次開啟還原
- **Mockup 對應**：`App` function（lines 821–886），但移除 mobile breakpoint（desktop-only per 2026-05-09 確認）
- **無 vertical state**（widths 是 ephemeral + localStorage）

### 2.2 `<DatasetPanel>` (Tier 3 custom)
- **Path**：`src/lib/components/data-analysis/DatasetPanel.svelte`
- **Mockup 對應**：`LeftPanel` (lines 156–358) — 視覺結構**直接採用**
- **Props**：
  ```ts
  export let chatId: string | null;        // 用來 update chat metadata
  export let selectedDatasetId: string;
  export let datasets: DatasetMeta[];
  export let activeGroupFilters: string[] = [];  // 多選 OR
  ```
- **Events**：
  ```ts
  dispatch('select-dataset', { datasetId: string })
  dispatch('toggle-group-filter', { groupId: string })
  dispatch('reset-filters')
  dispatch('refresh-datasets')
  ```
- **結構**（mockup LeftPanel pattern）：
  ```
  ┌─────────────────────────────────────┐
  │ [Group1] [Group2] [Group3] ...  [⟲] │  ← chip filter bar (lines 188–246)
  ├─────────────────────────────────────┤
  │ All Datasets · 24 items             │  ← header (lines 248–259)
  ├─────────────────────────────────────┤
  │ ▼ GROUP NAME                    12  │  ← collapsible group header (lines 273–297)
  │   ▼ 📂 Sub-category             5   │  ← sub-folder by dataset_type (lines 298–340)
  │     [icon] dataset-name             │
  │            12.4M rows · Apr 28      │  ← <DatasetRow> (lines 367–399)
  └─────────────────────────────────────┘
  ```
- **Sub-grouping by dataset metadata**：依 `DatasetMeta.dataset_type` 自動分組（CSV / SQLite / JSON / Parquet 等）— 對應 mockup `TYPE_SUBFOLDER`
- **Empty state**：見 mockup lines 344–353 — 大 emoji + "No datasets found"
- **Loading state**：`datasets === null` → skeleton 3 row
- **Error state**：`datasetError != null` → red banner 含 retry button → emit `refresh-datasets`

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

### 2.4a `<DatasetRow>` (Tier 3 custom，從 DatasetPanel 抽出)
- **Path**：`src/lib/components/data-analysis/DatasetRow.svelte`
- **Mockup 對應**：`FileRow` (lines 367–399)
- **Props**：
  ```ts
  export let dataset: DatasetMeta;
  export let groupColor: string;       // OKLCH from dataset.group
  export let selected: boolean;
  ```
- **Events**：`dispatch('select', { datasetId: string })`
- **Visual**：左 `<DatasetIcon>` + 中（name + row count mono）+ 右 (updated_at mono)
- **States**：hover / selected — 依 [frontend-design-tokens.md §Pattern](./frontend-design-tokens.md#pattern互動-state-視覺)

### 2.4b `<DatasetIcon>` (Tier 3 custom，視覺元件)
- **Path**：`src/lib/components/data-analysis/DatasetIcon.svelte`
- **Mockup 對應**：`FileIcon` (lines 96–112)
- **Props**：
  ```ts
  export let datasetType: string;  // 'csv' | 'sqlite' | 'json' | 'parquet' | ...
  export let size: 'sm' | 'md' = 'md';   // sm: 24×30 (header)、md: 36×44 (list)
  ```
- **Visual**：圓角 5px 框 + 對應 `--ds-{type}` 色彩（[design-tokens §Domain-specific 色彩](./frontend-design-tokens.md#domain-specific-色彩dataset-類型--chart-類型)）+ 底部 type uppercase

### 2.4c `<Resizer>` (Tier 3 custom，layout 工具)
- **Path**：`src/lib/components/data-analysis/Resizer.svelte`
- **Mockup 對應**：`Resizer` (lines 115–155)
- **Props**：
  ```ts
  export let side: 'left' | 'right';  // 視覺條對齊哪一邊
  export let onResize: (newClientX: number) => void;
  ```
- **Behavior**：
  - 7px 透明 hit zone（`position: absolute; top: 0; bottom: 0; [side]: -3px; width: 7px; cursor: col-resize`）
  - 內含 2px 視覺條，hover/drag 時 `opacity: 0.5; height: 100%`
  - mousedown → 全域 mousemove/mouseup 監聽 → 拖曳期間 `document.body.style.cursor` 與 `userSelect` 改寫
- **無 state** 除了 hov / drag 兩個 boolean
- **Caller 責任**：clamp newClientX 到合理範圍，update 寬度 store / prop

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

| 檔案 | 必要性 | 預估行數 | Mockup 對應 |
|---|---|---|---|
| `src/routes/(app)/workspace/data-analysis/+page.svelte` | P0 | ~200 | — |
| `src/routes/(app)/workspace/data-analysis/[id]/+page.svelte` | P0 | ~250 | `App` (lines 821–886) |
| `src/lib/components/data-analysis/DataAnalysisLayout.svelte` | P0 | ~80 | `App` flex layout |
| `src/lib/components/data-analysis/DatasetPanel.svelte` | P0 | ~280 | `LeftPanel` (156–358) |
| `src/lib/components/data-analysis/DatasetRow.svelte` | P0 | ~80 | `FileRow` (367–399) |
| `src/lib/components/data-analysis/DatasetIcon.svelte` | P0 | ~30 | `FileIcon` (96–112) |
| `src/lib/components/data-analysis/Resizer.svelte` | P0 | ~60 | `Resizer` (115–155) |
| `src/lib/components/data-analysis/CanvasFeed.svelte` | P0 | ~200 | `MiddlePanel` frame (lines 360–366), `ContentViewer` (412–483) header pattern |
| `src/lib/components/data-analysis/ChartCardCanvas.svelte` | P0 | ~180 | adapted from `ContentViewer` body |
| `src/lib/components/data-analysis/ChatPlaceholder.svelte` | P0 | ~70 | — (custom) |
| `src/lib/components/data-analysis/scroll-utils.ts` | P0 | ~30 | — |
| `src/lib/stores/data-analysis.ts` | P0 | ~80 | — |
| `src/lib/apis/data-analysis/index.ts` | P0 | ~60 | — |
| `src/lib/styles/data-analysis-tokens.css` | P0 | ~80 | from `frontend-design-tokens.md` |
| `src/lib/i18n/locales/{lang}/data_analysis.json` | P1 | n/a | — |

**合計：~1680 行**，14 個前端檔案。新增 `Resizer / DatasetIcon / DatasetRow` 是 mockup 的可重用元件，從 DatasetPanel 抽出來，比上次（~3000 行 + 自寫 streaming + 自寫 message thread）**少約 45%**，因為 reuse-first + 借 mockup design system。

> Hard cap **15 個檔案**。如果接近，回頭看哪個能再合併或從 mockup 抽到更高 reuse 層級。

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
