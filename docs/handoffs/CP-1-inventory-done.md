# Handoff — CP-1 Inventory Done

**Tag**: `inventory-done`
**Date**: 2026-05-10 09:18
**Agent**: Codex
**Branch HEAD**: `0d5a8f3e9`

> ⚠️ **Retroactive handoff**：CP-1 review 進行時 agent 未產出此 doc，由 reviewer (istale) 在 review 同時補錄。CP-2 起所有 checkpoint **必須** agent 自行產 handoff doc 並提交，不允許 reviewer 補。

---

## ✅ Done

- 讀完所有 Tier 1 模組（Chat / Messages / ResponseMessage / MessageInput / Chats model / Auth / Sidebar / Markdown stack）並紀錄具體 line numbers
- 讀完所有 Tier 2 模組（ContentRenderer / Markdown / FollowUps / Artifacts / ToolCallDisplay / models store）
- 確認 Tier 3 custom file 清單 = 13/13（cap 15）
- 完成 3 個 Day 1 必決定：Plan C (Chat) / Plan C (Sidebar) / FE-C 暫定 (ResponseMessage placeholder)
- ⚠️ 處理 ET-1 spec discrepancy（D-002）：自行更新 11 個 spec 檔案 align native `message.output[]` model（commit `6515d6b57`）
- Tag `inventory-done` 已建並 push

## 📊 Diff Summary

- Files changed (in 2 commits since CP-0): 12
- Lines added: +91 in spec align + 95 in inventory
- Lines removed: -64 in spec align + 94 in inventory
- Commits since `bootstrap-day-0`: 2
- Tier 3 file count so far: 13 / 15

```
0d5a8f3e9 spec: complete Day 1 inventory of Open WebUI modules
6515d6b57 spec: align tool-call persistence with Open WebUI output model
```

## ❓ Open Questions（已 resolved at review）

- Q1: Approve P-003 (Chat.svelte extra props + saveChatHandler) → ✅ Approved
- Q2: Approve P-002 (Sidebar entry + ChatItem routing) → ✅ Approved
- Q3: FE-C vs FE-B vs FE-D for placeholder → 🔀 DEFERRED to CP-3

## ⚠️ Risk Flags

- R1: Plan C × 3 means 3 core touches vs 1 pre-approved. Reviewer reduced to 2 active (P-002, P-003) + 1 pending (P-004 → CP-3 decision).
- R2: D-002 finding showed earlier specs assumed a frontend `message.toolCalls[]` field that doesn't exist in current Open WebUI. Spec docs updated in commit `6515d6b57`. **Risk**: future spec writers (or other agents) may reach for old patterns; the corrected docs need to remain authoritative.
- R3: `Chat.svelte` `saveChatHandler()` does not persist arbitrary metadata. Without P-003 extension, `chat.chat.metadata.workspace_type` would be dropped on save. P-003 scope explicitly extended at review to fix.
- R4: `process_tool_result()` strips `data:image/...` parts from frontend output (`middleware.py:4738-4755`). For chart rendering we MUST put image as URL via `function_call_output.files`, not as data URI in result.
- R5: No CP-1 handoff doc was produced; only inventory-results.md. Reviewer flagged this as a procedure deviation; CP-2+ must produce handoff docs.

## 🔍 Verify Steps

```bash
cd /Users/istale/Documents/open-webui-based-project

# 1. Inventory completeness
grep -c "✅ confirmed\|⚠️ confirmed" docs/spec/inventory-results.md
# expect ≥ 10

# 2. D-002 alignment — spec docs no longer reference frontend message.toolCalls[]
grep -rn "message\.toolCalls\b" docs/spec/ 2>/dev/null
# expect: only historical context references, none as authoritative claim

# 3. Plan decisions present
grep -A1 "決策：\*\*Plan" docs/spec/inventory-results.md | head -20

# 4. Tag exists
git tag | grep inventory-done
# expect: inventory-done

# 5. Verify D-002 finding against codebase
grep -n "message\.output\?\.\?length\|message\.output\[" src/lib/components/chat/Messages/ResponseMessage.svelte | head -3
# expect: confirms native uses message.output[]
```

## Decision Made

✅ **APPROVED** with conditions (resolved decisions for Q1/Q2/Q4, Q3 deferred to CP-3).

Documented in [`docs/review-log.md` 2026-05-10 CP-1 entry](../review-log.md).

---

## Next phase

CP-2 (Adapter Done) — Day 2-3 工作開始：

1. `backend/open_webui/utils/data_analysis/repository.py`（Port: DatasetRepository Protocol + DTOs + Errors）
2. `backend/open_webui/utils/data_analysis/adapters/in_memory_adapter.py`（含 fault injection 8 magic strings）
3. `backend/open_webui/utils/data_analysis/adapters/http_adapter.py`（含 retry + DTO transform + error mapping）
4. `backend/open_webui/utils/data_analysis/fixtures.py`
5. `tests/data_analysis/test_repository_contract.py`
6. `pytest tests/data_analysis/` 全綠

詳見 [`database-adapter.md`](../spec/database-adapter.md) 與 [`review-protocol.md` CP-2](../review-protocol.md#cp-2adapter-done)。

**Hard rules CP-2 期間：**
- Tool / route 程式 0 個 `import httpx`（adapter 內才能 import）
- DTO 全部 `frozen=True`
- 8 個 fault injection magic strings 各自有 unit test
- 完成必產 handoff `docs/handoffs/CP-2-adapter-done.md`
- Tag + push + 等 review 才 proceed CP-3
