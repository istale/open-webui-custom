# Frontend Design Tokens

> **來源**：`docs/design/3panel-mockup.html`（user-designed React 原型，2026-05-08）
> **用途**：vertical workspace 統一視覺語言。所有 Svelte 元件 CSS 一律用以下 CSS variables，禁止 hardcode 顏色。
>
> **重要**：這是 vertical workspace **內部**的 design system。Open WebUI 原生元件（`<Chat>`, `<MessageInput>` 等）沿用 Open WebUI 自身 theme。Vertical custom 元件用本檔。兩者互不污染。

---

## CSS Variables（在 `:root` 宣告）

### Light theme（預設）

```css
:root {
  --bg:           #f7f6f3;   /* 主背景 — 溫暖偏黃白 */
  --surface:      #ffffff;   /* 卡片 / 元件背景 */
  --surface2:     #f0efe9;   /* 次要 surface（hover、subtle bg） */
  --border:       #e4e2da;   /* 一般邊框 */
  --text:         #1a1916;   /* 主文字（暖近黑） */
  --text-muted:   #7a7870;   /* 次要文字 */

  --accent:       oklch(55% 0.18 250);   /* 主色 — 可由 user tweaks 改 */
  --accent-soft:  oklch(96% 0.04 250);
  --accent-border: oklch(80% 0.10 250);

  --chip-active-bg:   oklch(55% 0.18 250);
  --chip-active-text: #fff;
  --chip-bg:          #efefeb;
  --chip-text:        #3a3935;
  --chip-hover:       #e3e2dc;

  --radius:    10px;
  --radius-sm: 6px;
  --shadow:    0 1px 3px rgba(0, 0, 0, 0.07), 0 4px 16px rgba(0, 0, 0, 0.04);

  --font: 'DM Sans', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  --mono: 'DM Mono', ui-monospace, 'SF Mono', Consolas, monospace;
}
```

### Dark theme

```css
:root[data-theme="dark"] {
  --bg:           #141412;
  --surface:      #1d1c19;
  --surface2:     #262520;
  --border:       #2e2d29;
  --text:         #e8e6df;
  --text-muted:   #7a7870;
  --chip-hover:   #2a2925;
  /* accent 系列保持不變，OKLCH 在暗底也夠對比 */
}
```

切換策略：在 `<html>` 加 `data-theme="dark"`。同步 Open WebUI 原生 theme store（讀 `$colorScheme`）。

---

## Domain-specific 色彩（Dataset 類型 / Chart 類型）

借鏡 mockup 的 `EXT_COLORS` 模式（OKLCH，per-type 上色）。本專案 dataset 類型對應：

```css
:root {
  /* Dataset type colors */
  --ds-csv:    oklch(52% 0.18 155);  /* 綠 */
  --ds-sqlite: oklch(50% 0.10 200);  /* 灰藍 */
  --ds-json:   oklch(54% 0.20 22);   /* 橙紅 */
  --ds-parquet: oklch(50% 0.12 60);  /* 橄欖 */
  --ds-xlsx:   oklch(52% 0.18 145);  /* 綠 */
  --ds-arrow:  oklch(55% 0.17 290);  /* 紫 */
  --ds-other:  oklch(50% 0.05 250);  /* 中性 */

  /* Chart type accent (for badge / border in canvas card) */
  --chart-line:    oklch(55% 0.18 250);
  --chart-bar:     oklch(55% 0.16 160);
  --chart-scatter: oklch(55% 0.17 290);
  --chart-control: oklch(55% 0.18 25);   /* 製程監控紅，強調警示性 */
  --chart-spc:     oklch(55% 0.18 25);
  --chart-pareto:  oklch(54% 0.20 22);
  --chart-heatmap: oklch(50% 0.10 200);
  --chart-box:     oklch(52% 0.14 220);
  --chart-histogram: oklch(50% 0.12 60);
}
```

用法：
```css
.dataset-icon[data-type="csv"]    { color: var(--ds-csv); }
.canvas-card[data-chart-type="control"] {
  border-left: 3px solid var(--chart-control);
}
```

---

## Typography

| Token | 用途 | 範例 |
|---|---|---|
| `font-family: var(--font)` | 主要文字（標題、內文、按鈕）| Dataset 標題 |
| `font-family: var(--mono)` | 數值、檔案大小、ID、token count、timestamp、code | "12.4k tokens", "card-id-uuid", "Apr 28" |
| `font-size: 11px` + `letter-spacing: 0.07em` + `text-transform: uppercase` | Section heading（"TODAY", "FOLDER 1"）| group label |
| `font-size: 13px` + `font-weight: 500` | Body text default | dataset name |
| `font-size: 14–15px` + `font-weight: 600–700` | 標題 | panel header |
| `font-size: 10–11px` | 次要 metadata（badge, count） | model badge |

**字體載入**：DM Sans / DM Mono via Google Fonts（`<link rel="preconnect"... rel="stylesheet">`）。Open WebUI 原生若已載入字體 fallback 沒問題；若沒有則自行加 link。

---

## Spacing scale

固定 4px 倍數：4 / 6 / 8 / 10 / 12 / 14 / 16 / 20 / 24 / 32

無 px → rem 轉換（mockup 用 px，我們延續以維持精準）。

---

## Radius

| Token | 值 | 用途 |
|---|---|---|
| `--radius`    | `10px` | 卡片、面板、modal、主要 button |
| `--radius-sm` | `6px`  | 小按鈕、icon button、folder/sub-folder header button |
| `999px` | — | chip / badge（pill 形狀）|

---

## Shadow

```css
--shadow: 0 1px 3px rgba(0, 0, 0, 0.07), 0 4px 16px rgba(0, 0, 0, 0.04);
```

Hover / selected 卡片用此 shadow。**不要堆疊多層 shadow**（mockup 嚴守單層原則）。

Selected with accent halo（限主要按鈕）：
```css
box-shadow: 0 2px 8px color-mix(in srgb, var(--accent) 25%, transparent);
```

---

## Transition

| 場景 | duration | easing |
|---|---|---|
| Hover bg / border / color | `0.15s` | `ease` |
| Resizer visual feedback | `0.15s` | linear |
| Folder collapse arrow rotate | `0.15s` | linear |
| Refresh icon spin | `0.5s` | ease |
| ChartCardCanvas highlight 1.5s 淡出 | `1.5s` | ease |

統一用 CSS `transition: <prop> <duration> <easing>`，避免 keyframe 除非真的需要（如 spinner / bounce）。

---

## Pattern：互動 state 視覺

### 1. Hover state
- 改 `background` 從 `transparent` → `var(--chip-hover)` 或 `var(--surface)`
- **不要**動 transform / scale（visual jitter）

### 2. Selected state
- `background: color-mix(in srgb, ${categoryColor} 10%, var(--surface))`
- `border-color: ${categoryColor}`
- `box-shadow: var(--shadow)`
- Text color 跟著 categoryColor

### 3. Active filter chip
- `background: color-mix(in srgb, ${color} 10%, var(--surface))`
- `border: 1.5px solid ${color}`
- `color: ${color}`

### 4. 2-step 刪除確認
- Hover state 顯示 `<TrashIcon>` 按鈕
- 第一次點：button bg/color 變紅 + title 改成 "Click again to confirm"
- 第二次點（2 秒內）：執行刪除
- 2 秒過後 timeout 還原

### 5. Highlight match（搜尋）
```jsx
<mark style={{
  background: `color-mix(in srgb, ${accent} 25%, transparent)`,
  color: accent,
  borderRadius: 2,
  padding: '0 1px'
}}>{match}</mark>
```

---

## Pattern：可重用元件

### `<Resizer>`
- 7px 寬透明 hit zone（`absolute, top:0, bottom:0, [side]: -3, width: 7, cursor: col-resize`）
- 內含 2px 視覺條，`hover/drag` 時 `opacity: 0.5, height: 100%`，平常 `opacity: 0, height: 0`
- 拖曳期間：`document.body.style.cursor = "col-resize"; userSelect = "none"`
- Drag handler 用 `mousemove` + `mouseup` 全域監聽
- Mockup 範例：lines 115–155

我們用法：DatasetPanel ↔ CanvasFeed 之間、CanvasFeed ↔ Chat 之間。

### `<DatasetIcon type={...}>`（仿 mockup `<FileIcon>`）
- 36×44 圓角 5px 框
- Background: `color-mix(in oklch, ${typeColor} 12%, white)`
- Border: `1.5px solid color-mix(in oklch, ${typeColor} 30%, transparent)`
- 底部小字標籤（type uppercase, 8px mono）
- Mockup 範例：lines 96–112

### Chip filter bar
- Pill button: `padding: 4px 10px`, `border-radius: 999px`
- 6×6 圓點 inline 表 group color
- Reset icon button（28×28, radius 7, 旋轉動畫）
- Mockup 範例：lines 188–246

### Search input with `⌘K` shortcut
- Input 容器 `radius: 10px`, `border: 1px solid var(--border)`, `box-shadow: inset 0 1px 2px rgba(0,0,0,0.04)`
- 左側 search icon
- 右側：有值時顯示 X clear button；無值時顯示 `⌘K` 鍵帽提示
- `useEffect` 註冊 `cmd/ctrl+K` → `inputRef.current.focus()`
- Mockup 範例：lines 672–752

---

## Icons

Mockup 用內嵌 SVG：search / X / plus / pin / chat / trash。我們延續這個策略，**不要引入 icon library**（lucide / heroicons 等增加 bundle）。

需要的 icon 清單見 [frontend-spec.md §2](./frontend-spec.md) 各元件列表。SVG 直接寫在 component 內。

---

## 對 Open WebUI 原生元件的相容性

我們的 design tokens 跟 Open WebUI 的 Tailwind theme 是**兩個獨立 system**。原則：
- Vertical 路由 (`/workspace/data-analysis/*`) 內：vertical 元件用本檔 token；`<Chat>` native 元件用 Open WebUI 原生樣式
- 視覺風格不一致是**可接受的**（vertical 是不同 domain，使用者預期不同氛圍）
- 兩者**不互相覆蓋**：vertical CSS 用 scoped class（如 `.workspace-data-analysis .panel`）

如果 Open WebUI 全域 dark mode 開啟：vertical 同步切 `data-theme="dark"`。可由 `+page.svelte` 訂閱 `$colorScheme` store 轉發。

---

## 反 pattern

| 反 pattern | 正解 |
|---|---|
| Hardcode 顏色 `#3b82f6` | 用 `var(--accent)` |
| 用 `box-shadow: 0 0 0 2px ...` 模擬 border | 用 `border: 1.5px solid ...` |
| 多層 nested `box-shadow` | 一層 `var(--shadow)` 就夠 |
| 不同 transition duration 散落各處 | 統一用本檔 §Transition 表 |
| 自定 emoji icon | 用 inline SVG（mockup 風格）|
| 直接在 Svelte 元件 hardcode 36×44 | 抽 `<DatasetIcon>` reusable component |
