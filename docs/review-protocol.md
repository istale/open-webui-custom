# Review Protocol — Stop-and-Review Checkpoints

> **誰必讀**：Code Agent（執行）、PM/Lead（審查）、工程師（理解何時會被打斷）。
>
> **目的**：在每個關鍵階段強制停下來 review，避免滾雪球式錯誤。
>
> **政策**：到 checkpoint 必停，**不能擅自往下做**。Review 結論記錄到 [`review-log.md`](./review-log.md)。

---

## 為什麼需要這個

過去專案常見失敗模式：
- 工程師在 Day 1 做了一個錯誤決策（e.g. 自寫 `MessageThread.svelte`）
- 沒人 review，Day 2-7 都基於這個錯誤往上疊
- Day 7 review 整體時，發現要回退 5 天工作

每個 checkpoint 強制停下 = **錯誤最早發現，回退範圍最小**。對於團隊經驗有限 + 第一次接觸 Open WebUI 的情境，這個機制特別重要。

---

## 7 個必停點（Sequential — 按順序解鎖）

每個 checkpoint **完成上一個** + **trigger condition 滿足** 才能開始。Agent 必須產出 handoff doc 並 stop，等 user `✅ APPROVED → proceed` 才繼續下一階段。

### CP-1：Inventory Done
- **Tag**：`inventory-done`
- **對應 Day**：1
- **Trigger**：所有 Tier 1/2 模組讀完，3 個 Plan 決策填入 [`inventory-results.md`](./spec/inventory-results.md)
- **Required deliverables**：
  - `inventory-results.md` 全 ⏳ TODO 換成 ✅/⚠️/❌
  - Plan A/B/C 三個決策完成（Native Chat / Sidebar / ResponseMessage hook）
  - Discrepancies table 填齊（沒衝突也要寫「none」）
  - Tier 3 custom 檔案數 ≤ 15
  - Open Questions 至少 0 條（可空）
- **Review focus**：
  - Plan 決策合不合理？
  - 有沒有「我以為要 custom 但其實已有」的反例？
  - Tier 3 清單膨脹了嗎？
  - Discrepancies 有沒有需要先改 spec 的？

### CP-2：Adapter Done
- **Tag**：`adapter-done`
- **對應 Day**：2-3
- **Trigger**：Port + InMemory + HTTP（stub 即可）+ Fault injection + tests 全綠
- **Required deliverables**：
  - `backend/open_webui/utils/data_analysis/repository.py`（Port）
  - `backend/open_webui/utils/data_analysis/adapters/in_memory_adapter.py`
  - `backend/open_webui/utils/data_analysis/adapters/http_adapter.py`（含 retry / error mapping）
  - `backend/open_webui/utils/data_analysis/fixtures.py`
  - `tests/data_analysis/test_repository_contract.py` 全過
  - `pytest tests/data_analysis/` 輸出 log
  - Fault injection 8 個 magic strings 各有 unit test
- **Review focus**：
  - DTO `frozen=True` 嗎？
  - Tool / route 內 `import httpx` = 0 ？
  - Errors 有沒有正確 mapping？
  - Fault injection 跟 spec 一致嗎？

### CP-3：First Tool E2E
- **Tag**：`first-tool-e2e`
- **對應 Day**：4
- **Trigger**：`list_datasets` 從 LLM prompt 觸發，原生 chat dispatch 到 backend，結果出現在 assistant `message.output[]` 的 `function_call_output`
- **Required deliverables**：
  - `backend/open_webui/tools/data_analysis/tool_module.py`（至少 `list_datasets` method）
  - `backend/open_webui/tools/data_analysis/__init__.py`（含 `register_builtin_data_analysis_tool`）
  - `backend/open_webui/main.py` 加 `[core-touch]` startup hook（P-001）
  - 螢幕截圖 / curl log：完整 trace 從 prompt 到 tool result
  - `app.state.TOOLS` + `TOOL_CONTENTS` 雙寫驗證（手動跑一次 reload，看 live instance 是否被覆蓋）
- **Review focus**：
  - Spec auto-generation 真的 work 嗎？（method type hints + docstring → OpenAI spec）
  - `TOOL_CONTENTS` 雙寫有效嗎？
  - LLM 看到的 spec 不含 `__user__` 等內部參數？
  - `[core-touch]` commit prefix + UPSTREAM_PATCHES.md P-001 entry 都對齊？

### CP-4：All P0 Tools
- **Tag**：`tools-done`
- **對應 Day**：5
- **Trigger**：5 個 tool method + chart_renderer 9 種 chart_type + image endpoint + auth 全運作
- **Required deliverables**：
  - `tool_module.py` 全 5 個 method（list/query/render/summarize/get_schema）
  - `chart_renderer.py` 9 種 chart_type 全實作
  - `query_cache.py`
  - `routers/data_analysis.py`（含 `/charts/{id}.png` endpoint 與 auth）
  - `tests/data_analysis/` 各 method + chart_type unit tests
  - 跑一個 prompt「show monthly trend」→ PNG 出來，cURL `/charts/{id}.png` 看到圖
- **Review focus**：
  - 千萬點 render 真的不 downsample？
  - chart_type fallback 邏輯（control 沒 USL/LSL → mean ± 3σ）是否正確？
  - Image endpoint auth 走原生 `Depends(get_verified_user)`？
  - Cache miss 時 LLM 看到的 error 字串有「query_id expired」？

### CP-5：Event Ledger
- **Tag**：`ledger-done`
- **對應 Day**：part of 5/6（看實作順序）
- **Trigger**：DB migration + worker + 13 P0 events 整合 + soft delete
- **Required deliverables**：
  - Migration file: `<n>_add_data_analysis_events.py`
  - `models/data_analysis_events.py` + `bulk_insert` + `mark_deleted`
  - `utils/data_analysis/event_logger.py` + 背景 worker
  - `main.py` startup/shutdown hook（仍是同一個 `[core-touch]`，加 worker lifecycle）
  - Frontend data-analysis API client + 5 處 emit
  - Backend tool functions 整合 emit
  - 13 個 P0 events 各至少 1 筆 fixture
- **Review focus**：
  - Tool function 用 `asyncio.create_task(log_event(...))`，**不**等 await
  - Queue full 時 `log.warning` 而非 raise？
  - Frontend `/events` endpoint 有 whitelist？
  - Soft delete `is_deleted` flip 對嗎？
  - Graceful shutdown 設定（uvicorn / k8s 配置）有寫進部署 doc？

### CP-6：Frontend MVP
- **Tag**：`mvp-frontend`
- **對應 Day**：6
- **Trigger**：3 panel layout + canvas feed + native chat 整合 + auto-scroll + sidebar entry
- **Required deliverables**：
  - 14 個 frontend 檔案完整（依 [`frontend-spec.brief.md` §11](./spec/frontend-spec.brief.md)）
  - 5 個 frontend events emit 點全接（`workspace.opened` / `dataset.selected` / `prompt.submitted` / `chart.rendered` / `stream.aborted`）
  - 螢幕錄影：跑 [`frontend-spec.md` §1.8 step-by-step 12 步](./spec/frontend-spec.md#18-step-by-step-使用者流程從-0-到看到第一張圖)
- **Review focus**：
  - 0 個 `MessageThread.svelte` / `streamDataAnalysis.ts` 等反 pattern？
  - 沒 `import httpx`？
  - CSS 全用 design tokens，無 hardcoded color？
  - `{#key chatId}` 是否需要（依 inventory 結果）？
  - i18n strings 有 namespace？

### CP-7：Final MVP
- **Tag**：`mvp-day-7`
- **對應 Day**：7
- **Trigger**：全部 [`data-analysis-vertical-spec.md` §7 acceptance](./spec/data-analysis-vertical-spec.md#7-acceptance-criteria) 通過
- **Required deliverables**：
  - DOD checklist 全綠
  - Manual QA 跑過所有 acceptance criteria
  - `UPSTREAM_PATCHES.md` 反映實際所有 core touches
  - 部署文件（如何啟動 / 環境變數 / migration）
- **Review focus**：
  - Acceptance criteria 真的全過？
  - Core touches ≤ 預期數量？
  - `[core-touch]` commits 都記錄在 UPSTREAM_PATCHES？
  - Tests 覆蓋 P0 行為？

---

## 3 個事件觸發點（隨時可能發生，必停）

### ET-1：Spec Discrepancy
- **Trigger**：Agent 發現 codebase 行為跟 spec 不一致
- **Behavior**：
  - 立即停下，**不要假設 spec 是對的繼續做**
  - Spec 跟 code 有差 = 規格根基動搖，必須先校準
- **Handoff 內容**：
  - 哪份 spec 哪節
  - Codebase 實際行為
  - 三個假設：spec 過時 / spec 錯誤 / agent 誤讀（哪個最可能）
  - 建議的 spec 修正

### ET-2：Core Touch Needed
- **Trigger**：發現必須改動 native 檔案，且該變動**不是 P-001 pre-approved**
- **Behavior**：
  - 停下，產 handoff 列出 Plan A/B/C 各自成本
  - 等 user 決定（user 可能說「找 Plan A」或「同意 Plan C，加 P-XXX 到 UPSTREAM_PATCHES」）
- **Handoff 內容**：
  - 為什麼需要改 native（沒有 hook 機制？哪一行？）
  - Plan A/B/C 估算：成本、衝突風險、是否需 vertical 端配合
  - 推薦 plan
  - 若採用，UPSTREAM_PATCHES.md 新 entry 草稿

### ET-3：Scope Creep
- **Trigger**：滿足任一條件
  - Tier 3 frontend 檔案數 > 15
  - 工時超出該階段預估 30%
  - 發現新功能需求（spec 沒寫但 user 暗示要）
- **Behavior**：
  - 停下，整理目前狀態
  - User 決定砍 / 延後 / 擴大 scope
- **Handoff 內容**：
  - 觸發條件
  - 多出的範圍（檔案 / 功能 / 時間）
  - Cut（砍）/ Defer（延後）/ Expand（擴大）三選項估算

---

## Handoff Doc Template

每個 checkpoint agent 必須產出一份 markdown，貼進 review session（或 commit 到 `docs/handoffs/CP-X-<tag>.md`）。

```markdown
# Handoff — CP-<#> <Name>

**Tag**: `<tag-name>`
**Date**: YYYY-MM-DD HH:MM
**Agent**: <agent identifier>
**Branch HEAD**: <commit hash>

---

## ✅ Done

<what was completed, bullet form, mapped to required deliverables>

## 📊 Diff Summary

- Files changed: <count>
- Lines added: <+N>
- Lines removed: <-N>
- Commits since last checkpoint: <count>
- Tier 3 file count so far: <n> / 15

```bash
git log --oneline <prev-tag>..<this-tag>
```
<paste output>

## ❓ Open Questions

<list of decisions that need user input. e.g.
- Q1: <question>
- Q2: <question>>

If none: "None."

## ⚠️ Risk Flags

<things agent noticed but isn't sure about. e.g.
- R1: ResponseMessage refactor changed attachment shape; verify Day 6 still works
- R2: Tier 3 count is 14, very close to cap>

If none: "None."

## 🔍 Verify Steps (for reviewer)

<concrete commands the user can run to validate>

```bash
# e.g.
cd /Users/istale/Documents/open-webui-based-project
pytest tests/data_analysis/ -v
```

## Decision Awaited

Pick one:
- ✅ APPROVED → proceed to CP-<next>
- ✏️ REVISE → specific feedback
- 🔀 PIVOT → re-direction

**Next phase brief (if approved)**:
<2-3 lines what agent will do next>
```

---

## Review Outcome — 3 種選項

User 對 handoff 回應**只能**是這三種其一（不能模糊）：

### ✅ APPROVED
```
✅ APPROVED → proceed to CP-3 (First Tool E2E)
```
- Agent 立刻進下一階段
- Review log 加 entry 記為 APPROVED

### ✏️ REVISE
```
✏️ REVISE
- Fix: query_dataset 沒處理 timeout fault injection
- Fix: 缺 idempotency test
- Re-submit handoff after fix
```
- Agent 修完重新 submit 同一 checkpoint
- 不解鎖下一階段
- Review log 加 entry 記為 REVISE + 列出修改項

### 🔀 PIVOT
```
🔀 PIVOT
- 改採 Plan B（mock server）取代 InMemory
- 影響 CP-2 / CP-3 都要重做
- 詳細：<具體說明>
```
- 重大方向改變，可能：
  - 跳過某個 checkpoint
  - 回頭做之前的（重新打開）
  - 整個重新規劃下一段
- Review log 加 entry 記為 PIVOT + 影響的 checkpoints

---

## 紀錄到 [`review-log.md`](./review-log.md)

每次 review 結束加一筆。Agent 看 log 就知道整個專案 review 軌跡。格式：

```markdown
## YYYY-MM-DD HH:MM — CP-<#> <Name>

- **Agent**: <id>
- **Branch HEAD before review**: <commit>
- **Outcome**: ✅ APPROVED / ✏️ REVISE / 🔀 PIVOT
- **Reviewer notes**:
  <2-5 lines, why approved / what to fix / pivot reason>
- **Next phase**: CP-<next> or "back to CP-<n> for revisions"
```

---

## Anti-pattern（review 流程本身的反模式）

| 反 pattern | 為什麼錯 |
|---|---|
| Agent 自己決定可以 skip checkpoint | 違反強制同步原則，回到滾雪球錯誤 |
| Review outcome 模糊（「大致 OK 但...」）| 三選項硬規則，避免 agent 不知道下一步 |
| Handoff 不寫 Risk Flags | Risk 隱形累積 = 未來爆炸 |
| Review log 不及時更新 | 失去軌跡，下個 reviewer 不知道前情 |
| Critical bug 等 CP-7 才發現 | 應該在 ET-1/2/3 觸發點隨時 raise |
| User 改了方向但沒 PIVOT 紀錄 | 後人不知道為什麼某個 spec 跟現實不符 |

---

## 給 user 的快速 review checklist

每次收到 handoff，照這個跑（5–15 分鐘）：

1. **讀 ✅ Done**：對照 Required deliverables 是否真的都做了？
2. **看 📊 Diff Summary**：commit 數合理？檔案數沒爆？
3. **跑 🔍 Verify Steps**：1–2 條，看是否真的 work
4. **掃 ⚠️ Risk Flags**：有沒有讓你警覺的？
5. **看 ❓ Open Questions**：能立刻回答嗎？
6. **抽查一個 commit diff**：隨機看一個 commit message + diff 對齊度
7. **下決定**：✅ APPROVED / ✏️ REVISE / 🔀 PIVOT

如果 5 分鐘內無法做決定 → 通常是 handoff 寫得不清楚，要 agent 補資料再 review，不要硬推。

---

## 可選：Pre-commit hook 自動驗證 checkpoint 完整性

之後可加 `.git/hooks/pre-tag` 或 CI workflow 自動檢查：

```bash
# tag 'inventory-done' 必須存在 docs/handoffs/CP-1-inventory-done.md
# tag 'tools-done' 必須包含 6+ commits since 'first-tool-e2e'
# 等等
```

降低 agent 漏跑流程的風險。MVP 不必，下個迭代加。
