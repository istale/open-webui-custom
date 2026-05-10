# Review Log — Vertical Workspace Project

> **目的**：累積所有 review checkpoint 的決策軌跡。每次 review 結束**必須**加 entry。
>
> **Reading direction**：最新在最上面（reverse chronological）。
>
> **誰加 entry**：reviewer（user / PM / lead），不是 agent。Agent 提交 handoff 後等 user 補 entry。
>
> **協議**：[`review-protocol.md`](./review-protocol.md)

---

## 範本（複製後填）

```markdown
## YYYY-MM-DD HH:MM — CP-<#> <Name>

- **Agent**: <agent identifier / model>
- **Branch HEAD before review**: <full commit hash>
- **Handoff doc**: `docs/handoffs/CP-X-<tag>.md` 或對話 paste
- **Outcome**: ✅ APPROVED / ✏️ REVISE / 🔀 PIVOT
- **Reviewer**: <name>
- **Reviewer notes**:
  <2–5 lines, 為什麼 APPROVED / 要修什麼 / 為什麼 PIVOT>
- **Critical decisions made**:
  <若有重大決策，例如「採 Plan C 改 Sidebar.svelte」>
- **Next action**:
  - 若 APPROVED → CP-<next>
  - 若 REVISE → list 具體修改項
  - 若 PIVOT → 影響哪些 checkpoint，新方向
```

---

## Entries

<!-- 最新加在最上面，最舊在下面 -->

## 2026-05-09 — Project Bootstrap (pre-CP-1)

- **Status**: 規格全部凍結，雙版本系統建立完畢
- **Branch HEAD**: `7b61e77a7`（spec: incorporate upstream sync findings）
- **Tag**: `bootstrap-day-0`
- **Notes**:
  - 規格 11 commits，0 application code
  - Upstream sync 完成，11 ahead / 0 behind
  - TOOL_CONTENTS 機制已寫入 spec
  - Day 1 inventory 待 agent 開始
- **Next action**: 等 CP-1 (Inventory) 啟動 — 預計需要 1 個工作日
- **Reviewer**: istale

<!-- 之後 entries 加在這條之上 -->
