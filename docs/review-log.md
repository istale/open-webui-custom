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

## 2026-05-10 — CP-1 Inventory Done

- **Agent**: Codex
- **Branch HEAD before review**: `0d5a8f3e9`
- **Tag**: `inventory-done`
- **Handoff doc**: ⚠️ 未產出 `docs/handoffs/CP-1-inventory-done.md`（agent 直接以 `inventory-results.md` 為交付）— 此 review 同時補產出 retroactive handoff
- **Outcome**: ✅ APPROVED with conditions
- **Reviewer**: istale

### Reviewer notes

Inventory 本身品質高（5/5）— Tier 1/2 模組讀到具體 line number、3 個 Plan 決策有 code evidence、Tier 3 = 13/13 守住 cap。最有價值的發現：D-002（spec 假設的 `message.toolCalls[]` 不存在；native 用 `message.output[]` + `<details type="tool_calls">` 序列化 HTML）— agent 自行處理 ET-1 spec 校準（commit `6515d6b57`，11 spec files 改動），行為對。

### Critical decisions

| Q | Decision |
|---|---|
| Q1 P-002 Sidebar `[core-touch]` | ✅ Approved。Hook 寬度 ≤ 5 行；vertical entry 加在 sidebar，ChatItem 路由依 `metadata.workspace_type` 切到 `/data-analysis/{id}` |
| Q2 P-003 Chat.svelte `extraToolIds` + `extraMetadata` props | ✅ Approved。**範圍擴大**：同 commit 內順便擴展 `saveChatHandler` 把 metadata 寫進 `chat.chat`，避免另寫 API 路徑 |
| Q3 ResponseMessage placeholder (FE-A/B/C/D) | 🔀 **DEFERRED to CP-3**。CP-2 (adapter) 不依賴此決定；CP-3 first-tool-e2e 跑出來後，看 native ToolCallDisplay 實際渲染結果，再決定 FE-D（tool 不放 file）/ FE-B（小 core touch 加 hook）/ FE-C（fallback）哪個最合適 |
| Q4 CP-1 handoff doc | ✅ Required retroactively。CP-2 起所有 checkpoint 必產 `docs/handoffs/CP-X-<tag>.md` |

### Next phase

CP-2 (Adapter Done) — agent 開始 Day 2-3 工作：DatasetRepository Port + InMemory + HTTP adapter + fault injection + tests。預計 1.5–2 天。

完成 trigger：`pytest tests/data_analysis/` 全綠 + 8 個 magic strings 都有 unit test。

---

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
