# Frontend Design Tokens — Brief / Contract Version

> **Quick reference of `frontend-design-tokens.md`. Read teaching version for principle and pattern explanations.**

---

## Light theme（`:root`）

```css
--bg:           #f7f6f3;
--surface:      #ffffff;
--surface2:     #f0efe9;
--border:       #e4e2da;
--text:         #1a1916;
--text-muted:   #7a7870;

--accent:       oklch(55% 0.18 250);
--accent-soft:  oklch(96% 0.04 250);
--accent-border:oklch(80% 0.10 250);

--chip-active-bg:   oklch(55% 0.18 250);
--chip-active-text: #fff;
--chip-bg:          #efefeb;
--chip-text:        #3a3935;
--chip-hover:       #e3e2dc;

--radius:    10px;
--radius-sm: 6px;
--shadow:    0 1px 3px rgba(0,0,0,0.07), 0 4px 16px rgba(0,0,0,0.04);

--font: 'DM Sans', system-ui, -apple-system, sans-serif;
--mono: 'DM Mono', ui-monospace, 'SF Mono', monospace;
```

## Dark theme（`:root[data-theme="dark"]`）

```css
--bg:         #141412;
--surface:    #1d1c19;
--surface2:   #262520;
--border:     #2e2d29;
--text:       #e8e6df;
--text-muted: #7a7870;
--chip-hover: #2a2925;
```

切換：`<html data-theme="dark">`，同步原生 `$colorScheme`。

---

## Domain colors

### Dataset types
```css
--ds-csv:    oklch(52% 0.18 155);
--ds-sqlite: oklch(50% 0.10 200);
--ds-json:   oklch(54% 0.20 22);
--ds-parquet:oklch(50% 0.12 60);
--ds-xlsx:   oklch(52% 0.18 145);
--ds-arrow:  oklch(55% 0.17 290);
--ds-other:  oklch(50% 0.05 250);
```

### Chart types
```css
--chart-line:     oklch(55% 0.18 250);
--chart-bar:      oklch(55% 0.16 160);
--chart-scatter:  oklch(55% 0.17 290);
--chart-control:  oklch(55% 0.18 25);    /* alarm-leaning red */
--chart-spc:      oklch(55% 0.18 25);
--chart-pareto:   oklch(54% 0.20 22);
--chart-heatmap:  oklch(50% 0.10 200);
--chart-box:      oklch(52% 0.14 220);
--chart-histogram:oklch(50% 0.12 60);
```

---

## Typography

| Token | 用法 |
|---|---|
| `font-family: var(--font)` | 主要文字 |
| `font-family: var(--mono)` | 數值、ID、timestamp、code |
| 11px + 0.07em letter + uppercase | Section heading |
| 13px + 500 | Body default |
| 14–15px + 600–700 | 標題 |
| 10–11px | Metadata badge |

字體：DM Sans / DM Mono via Google Fonts。

---

## Scale

- Spacing: 4 / 6 / 8 / 10 / 12 / 14 / 16 / 20 / 24 / 32 (4px multiples)
- Radius: `--radius` 10px, `--radius-sm` 6px, `999px` (chip pill)
- Shadow: 單層 `--shadow`，禁止堆疊
- Selected halo (button only): `0 2px 8px color-mix(in srgb, var(--accent) 25%, transparent)`

## Transition

| 場景 | duration | easing |
|---|---|---|
| Hover bg/border/color | 0.15s | ease |
| Resizer feedback | 0.15s | linear |
| Folder collapse arrow | 0.15s | linear |
| Refresh icon spin | 0.5s | ease |
| Highlight 1.5s 淡出 | 1.5s | ease |

---

## State patterns

### Hover
- Change bg / border / shadow only
- No transform / scale

### Selected
```css
background: color-mix(in srgb, ${categoryColor} 10%, var(--surface));
border-color: ${categoryColor};
box-shadow: var(--shadow);
color: ${categoryColor};
```

### Active filter chip
```css
background: color-mix(in srgb, ${color} 10%, var(--surface));
border: 1.5px solid ${color};
color: ${color};
```

### 2-step delete confirm
- Hover → trash icon visible
- 1st click → button bg/color red + title "Click again to confirm"
- 2nd click within 2s → execute delete
- Else timeout 2s → reset

### Search highlight `<mark>`
```css
background: color-mix(in srgb, var(--accent) 25%, transparent);
color: var(--accent);
border-radius: 2px;
padding: 0 1px;
```

---

## Reusable components

### `<Resizer>`
- 7px transparent hit zone
- 2px visual bar, hover/drag opacity 0.5 + height 100%
- mousedown → window mousemove/mouseup, body cursor + userSelect override

### `<DatasetIcon>`
- 36×44 (md) / 24×30 (sm), radius 5px
- `bg: color-mix(in oklch, ${typeColor} 12%, white)`
- `border: 1.5px solid color-mix(in oklch, ${typeColor} 30%, transparent)`
- 底部 type uppercase 8px mono label

### Chip filter bar
- pill button: padding 4px 10px, radius 999px
- 6×6 round dot for group color
- Reset icon button 28×28 radius 7px, rotate animation on click

### Search input + ⌘K
- Container: radius 10, border 1px, inner shadow
- Left: search icon
- Right: X clear (when value) / `⌘K` chip (when empty)
- `useEffect` registers `cmd/ctrl+K` → focus

---

## Icons

Inline SVG, no library. Mockup 提供：search / X / plus / pin / chat / trash / 旋轉 (refresh)。

---

## Compatibility with native Chat

- Vertical CSS scope: `.workspace-data-analysis` 內套這些 tokens
- Native Chat 內保持原生 Tailwind theme，**不互覆蓋**
- Dark mode 同步原生 `$colorScheme` store

---

## Anti-patterns

- ❌ Hardcode color → `var(--token)`
- ❌ Stacked shadows → 單層
- ❌ Different transition durations → 用本表
- ❌ Use emoji as icon → inline SVG
- ❌ 寫死 36×44 → 用 `<DatasetIcon>`
- ❌ Vertical CSS 污染原生 Chat → 用 scope class

---

## 跨檔關聯

- 元件契約：[`frontend-spec.brief.md`](./frontend-spec.brief.md)
- 視覺來源：[`docs/design/3panel-mockup.html`](../design/3panel-mockup.html)
