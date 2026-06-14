# Mockup Analysis — `3panel-mockup.html`

> **來源**：user-designed React 原型，2026-05-08
> **檔案**：[`3panel-mockup.html`](./3panel-mockup.html)（單檔 standalone，內嵌 React + Babel runtime + base64 fonts）
> **解碼版本**：~900 行 JSX（不含 fonts），記憶體中已解析

---

## Tech Stack（Mockup 自身）

- **React 18** + ReactDOM `createRoot` (in-browser Babel for JSX)
- 純 inline styles（無 CSS class）— 之後 port 到 Svelte 時需轉 CSS
- React 22 hooks: `useState`, `useRef`, `useEffect`
- Custom helpers: `useTweaks` (light/dark + accent picker debug panel — 開發用，production 移除)

---

## 三 panel 結構

| Panel | Width | 內容 | Mockup function |
|---|---|---|---|
| **Left** | 300px (200–560 resizable) | Folder chip filter + folder tree + sub-folder by file type + file row | `LeftPanel` |
| **Middle** | flex-1 | File preview header + content body (pre-formatted) | `MiddlePanel` + `ContentViewer` |
| **Right** | 320px (240–560 resizable) | Chat history list（搜尋 / group by date / 2-step 刪除 / New Chat 按鈕）| `RightPanel` + `ChatItem` |

---

## 元件清單

| Mockup function | 對應我們 vertical 元件 | 適用範圍 |
|---|---|---|
| `App` | `+page.svelte` | layout root |
| `LeftPanel` | `DatasetPanel.svelte` | direct map |
| `MiddlePanel` + `ContentViewer` | `CanvasFeed` + `ChartCardCanvas` | **重組** — mockup 是單一 file viewer，我們是多卡片 feed |
| `RightPanel` + `ChatItem` | **目前選 Plan A**：mockup 此 panel 不直接落地，視覺借用至**未來 sidebar 的 chat list** | 待 user 決定（見下方）|
| `Resizer` | `Resizer.svelte` | direct map（pure adoption）|
| `FileIcon` | `DatasetIcon.svelte` | direct map |
| `FileRow` | `DatasetRow.svelte` | direct map |
| `IconSearch` / `IconX` / `IconPlus` / `IconPin` / `IconChat` / `IconTrash` | inline SVG 各 component 內 | 不抽 icon library |
| `useTweaks` (debug panel) | **不採用**（production 不要 debug panel）| — |

---

## 視覺 Design System → 抽出到 [frontend-design-tokens.md](../spec/frontend-design-tokens.md)

- 色彩：`--bg / --surface / --surface2 / --border / --text / --text-muted` + accent + chip 系列 + dark mode
- 字體：DM Sans / DM Mono
- Domain 色（per dataset / chart type）：OKLCH-based
- Radius / shadow / transition duration table

---

## 互動模式（已抽進 frontend-design-tokens.md §Pattern）

1. **Chip filter**：多選 OR 邏輯、reset button 旋轉動畫
2. **Folder collapse**：箭頭旋轉、count 顯示
3. **File select**：tinted bg + colored border + box-shadow
4. **Search highlight**：inline `<mark>` with color-mix bg
5. **2-step delete confirm**：第一次紅 button + title 提示，2 秒 timeout 還原
6. **⌘K shortcut**：focus search input
7. **Resizer drag**：document.body.style cursor + userSelect 改寫，mousemove/mouseup 全域監聽
8. **Refresh icon spin**：`transform: rotate(-360deg)` 0.5s

---

## 假資料（mockup 含，實作時 100% 移除）

```
FOLDERS = [Folder 1/2/3 with colors]
FILES = [9 個假檔案]
EXT_COLORS, TYPE_SUBFOLDER, SUBFOLDER_ORDER
FILE_CONTENT = {filename: text}
SAMPLE_CHATS = [11 個假 chat record]
```

實作時這些一律從原生 store / API 拿：
- folders → `getFolders()` API
- datasets → `list_datasets` tool result（vertical 自身）
- chats → `chats` store（原生）
- chat metadata → `chat.chat.metadata.data_analysis.*`

---

## ⚠️ 重要 layout 差異（待 user 確認）

Mockup 的 RIGHT panel = **chat history list**。我們 frontend-spec §2 的 RIGHT panel = **native `<Chat>` 對話本身**。

三種解讀：

| 解讀 | Right panel | Active chat 跑哪 | 含意 |
|---|---|---|---|
| **A. 視覺借用**（**目前採用**）| 仍是 native `<Chat>` (live) | 右欄 | Mockup 純參考設計 tokens / 元件風格，layout 不變 |
| **B. Mockup 即規格** | Chat history list | Middle 替換或 modal | 重組 layout，charts 跑去哪需重新設計 |
| **C. 雙模式** | 預設 history list；點 chat 後切成 live Chat | 同右欄 | Right panel 是 history ↔ live 切換 |

**目前採 A**（與 vertical 規格 "分析過程記錄都要保留" 一致；charts 需要中間欄整版空間）。

**若要改 B 或 C**，需更新：
- `frontend-spec.md` §2 重新定義 RIGHT panel
- `inventory-results.md` 加新的 Plan 對照
- `data-analysis-vertical-spec.md` §1 三 panel layout 圖

---

## 採用 vs 不採用對照

### ✅ 採用（直接抽進 frontend-design-tokens.md / frontend-spec.md）
- 色彩 system（含 dark mode）
- 字體（DM Sans / DM Mono）
- Radius / shadow / transition tokens
- LeftPanel 的 chip filter + folder tree 結構
- FileIcon 視覺
- Resizer 元件
- 搜尋 ⌘K shortcut + highlight
- 2-step delete pattern
- 中間欄空狀態 placeholder（"Select a [X] to preview"）

### ❌ 不採用 / 暫緩
- `useTweaks` debug panel（production 不要）
- Mockup 的 chat history list 結構（Plan A 下不在 right panel；未來可移到 sidebar 用）
- React inline styles（Svelte 用 CSS modules / scoped style）

### 🟡 重組
- Mockup MIDDLE = single file preview → 我們是 multi-card chart feed
  - 採用：header + body 框架、空狀態 placeholder
  - 重組：body 內容從 `<pre>` 改為 `<ChartCardCanvas>` 列表

---

## 影響哪些 spec docs

| Spec doc | 變動 |
|---|---|
| `frontend-design-tokens.md` | **新建** — 抽出 mockup 的 design system |
| `frontend-spec.md` | 加入 Resizer / DatasetIcon 元件契約；DatasetPanel 結構參照 mockup LeftPanel |
| `data-analysis-vertical-spec.md` | 不變（domain 規格不受視覺影響）|
| `inventory-results.md` | Day 1 多一個決策：mockup layout interpretation A/B/C |
| `tools-schema.md` | 不變 |
| `database-adapter.md` | 不變 |
