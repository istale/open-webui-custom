# UPSTREAM PATCHES — Open WebUI Fork 維護日誌

> **目的**：追蹤所有 `[core-touch]` 修改（即任何動到 Open WebUI 原生檔案的變動），讓未來月度 `git rebase upstream/main` 時有 single checklist 可走。
>
> **規則**：
> - 任何 commit 訊息包含 `[core-touch]` 必須在此檔加 entry
> - 任何 entry 變動（新增 / 移除 / 修改）必須在 PR description 提及
> - 月檢查時 walk through 此檔每個 entry，確認是否仍需要 / 仍正確
>
> **相關規格**：[`docs/spec/PROJECT_GUIDE.md` Core Touch Discipline](./spec/PROJECT_GUIDE.md#core-touch-discipline-fork-維護關鍵)

---

## 為什麼要做這個

Open WebUI 是快速迭代的開源專案（每週數次 commit）。我們的 fork 每月會 rebase upstream 拉新 features / fixes。**我們的 `[core-touch]` 改動每次 rebase 都會跟 upstream 衝突**。

如果沒有此 checklist，rebase 時會：
- 漏掉某個 patch（例：`Sidebar.svelte` 的 vertical entry）→ 功能默默失效
- 重複 patch（例：upstream 自己加了 hook，我們還繼續維護自己的 patch）→ 維護成本上升
- 不知道某個 patch 的「為什麼必須改」 → 無法判斷能否 revert

此檔解決這三件事。

---

## 月度 Rebase Checklist

每次 `git fetch upstream && git rebase upstream/main` 前：

```bash
# 1. 列出所有 [core-touch] commits 對照本檔
git log --oneline | grep '\[core-touch\]'

# 2. 對每個 entry 逐一驗證:
#    - 修改的檔案 upstream 最近有沒有改動？git log upstream/main -- <file>
#    - 我們的 hook 行範圍是否還對得上？
#    - upstream 是否已經自己加了等價 hook（→ 我們的 patch 可移除）？

# 3. Rebase
git rebase upstream/main

# 4. 解 conflict 後跑完整 test
pytest backend/
npm test
```

每個 entry 驗證後，若有變動：
- ⚠️ Entry 修改 → 更新本檔（commit prefix `chore(upstream-sync): ...`）
- ✅ Entry 已不需要 → revert 對應 commit + 從本檔移除 entry
- ❌ Entry 衝突嚴重 → 暫停 rebase，找出 upstream 改了什麼，討論是否要走 Plan B/C

---

## Active Patches

### Pre-approved (規格內預設)

#### P-001 — Vertical Tool Registration Startup Hook
- **Status**: ✅ Active
- **File**: `backend/open_webui/main.py`
- **Lines**: ~5 lines（見 commit）
- **Commit prefix**: `[core-touch]`
- **First introduced**: 2026-05-11 (`a608bb6d6` — `[core-touch] feat: register data analysis list_datasets tool`)
- **Why required**:
  Open WebUI 沒有 tool plugin / dynamic registration API。Tools 必須存在 DB 表中。
  最乾淨方式：在既有 `lifespan(app)` startup path 把我們 vertical 自帶的
  `class Tools` 寫進 DB 並 warm `app.state.TOOLS` cache。詳見
  [`tools-schema.md` 「整合 Open WebUI 的 Tool Registration」](./spec/tools-schema.md#整合-open-webui-的-tool-registration已實際確認)。
- **Plan tier**: Plan B（無 native hook，但寬度極小）
- **Owner**: vertical/data-analysis backend
- **Related spec**: [`tools-schema.md`](./spec/tools-schema.md)、[`tools-schema.brief.md`](./spec/tools-schema.brief.md)
- **Removal condition**:
  Upstream 加了 `register_builtin_tool(...)` API → 改用 native API + revert 此 hook
- **Code snippet** (參考用，實際以 commit diff 為準):
  ```python
  from open_webui.tools.data_analysis import register_builtin_data_analysis_tool
  await register_builtin_data_analysis_tool(app)
  ```
- **Upstream interaction notes** (post-sync 2026-05-09 to `f51d2b026`):
  - 2026-05-11 CP-3 correction: current `main.py` is already wired through
    `FastAPI(lifespan=lifespan)`, so P-001 must live inside that existing
    lifespan startup block before `app.state.startup_complete = True`; a
    separate `@app.on_event("startup")` handler is not the correct hook.
  - Upstream 加了 `app.state.TOOL_CONTENTS = {}` (`main.py:983`) +
    cache invalidation logic (`utils/tools.py:194-198`)
  - 我們的 `register_builtin_data_analysis_tool` 必須**同時**設
    `app.state.TOOL_CONTENTS[BUILTIN_TOOL_ID] = content`，否則第一次
    tool resolution 時會把 live instance 替換成 DB-exec 出來的
  - 此調整已寫入 [`tools-schema.md`](./spec/tools-schema.md)
    與 [`tools-schema.brief.md`](./spec/tools-schema.brief.md)

---

### Active — promoted from Day 1 inventory (2026-05-10)

#### P-002 — Sidebar Entry for Vertical Workspace
- **Status**: ✅ Active (approved CP-1) — to be implemented in CP-6 (Frontend MVP)
- **File**: `src/lib/components/layout/Sidebar.svelte`
- **Plan tier**: Plan C（confirmed by inventory — no plugin / dynamic registration mechanism in current upstream `f51d2b026`，hard-coded `DEFAULT_PINNED_ITEMS` 等 list）
- **Approval**: 2026-05-10 by user via review-log
- **Why required**:
  - Sidebar 是進入 vertical workspace 的入口
  - Inventory 確認 sidebar 沒有 plugin / dynamic registration（`Sidebar.svelte:78-150` `DEFAULT_PINNED_ITEMS` + `isMenuItemVisible()` + `getMenuItemMeta()` 全是 hard-coded）
  - 同時 `Sidebar/ChatItem.svelte:448-471` 把 chat anchor `href` hard-code 成 `/c/{id}`
- **Intended hook（≤ 5 行 in Sidebar.svelte，外加 ChatItem 條件）**:
  - Sidebar.svelte: 加 1 個 vertical NavItem 連到 `/data-analysis`
  - ChatItem.svelte: 修改 `href` 計算邏輯，依 `chat.chat.metadata.workspace_type` 決定路由（`/data-analysis/{id}` vs `/c/{id}`）
- **Owner**: vertical/data-analysis frontend (CP-6)
- **Related spec**: [`frontend-spec.md` §1.4](./spec/frontend-spec.md#14-sidebar-entry--怎麼加-data-analysis-入口) / §1.7
- **Removal condition**:
  - Upstream 提供 `registerSidebarEntry(...)` API → revert + use native
  - Upstream sidebar 改成 dynamic config-driven → revert + add config

#### P-003 — Chat.svelte Extra Props + saveChatHandler Metadata Persistence
- **Status**: ✅ Active (approved CP-1) — to be implemented in CP-6 (Frontend MVP)
- **File**: `src/lib/components/chat/Chat.svelte`
- **Plan tier**: Plan C（confirmed by inventory — `Chat.svelte:115` only exports `chatIdProp`, no `tool_ids`/`metadata` accept; `selectedToolIds` is locally owned `:151`; `navigateHandler()` `:193-252` resets it on every chat load; `saveChatHandler()` `:2808-2817` only persists `models/history/messages/params/files`，drops arbitrary metadata）
- **Approval**: 2026-05-10 by user via review-log
- **Why required**:
  - 需要把 `tool_ids: ['builtin:data-analysis']` 注入 chat completion payload
  - 需要把 `metadata: { workspace_type: 'data-analysis', selected_dataset_id: ... }` 寫入 `chat.chat`
  - Plan B (fetch interceptor) 不能解決 native URL replacement（`/c/{id}`）也不解決 metadata persistence
- **Intended hook**（單一 `[core-touch]` commit，~5–8 行）:
  - 加 2 個 export props：`extraToolIds: string[] = []`、`extraMetadata: Record<string, any> = {}`
  - `submitHandler` 內把 `extraToolIds` 合進送出 payload 的 `tool_ids`
  - `saveChatHandler` 內把 `extraMetadata` merge 進 `chat.chat.metadata`（不覆寫既有 keys）
  - `navigateHandler` 內讀 chat document 的 `metadata.workspace_type`，若為 vertical 就跳 `/data-analysis/{id}` 取代 `/c/{id}` URL replace
- **Owner**: vertical/data-analysis frontend (CP-6)
- **Related spec**: [`frontend-spec.md` §9](./spec/frontend-spec.md) Plan A/B/C decision
- **Removal condition**:
  - Upstream 加 `Chat.svelte` 接受 props 之一 → revert + use native
  - Vertical 改用獨立 `<Chat>` (fork-and-replace) → revert this hook（但成本更高，不推薦）

### Pending — deferred decisions

#### P-004 — Chart Placeholder Render Path
- **Status**: ⏳ DEFERRED to CP-3 (First Tool E2E)
- **Decision rationale**:
  CP-1 inventory 提議 FE-C（CSS hide + DOM inject）。Reviewer 觀察 FE-D（tool 不放 file，靠文字 placeholder + canvas 獨立 fetch）可能更乾淨，但需 CP-3 看 native ToolCallDisplay 實際渲染才能定。
- **Options to evaluate at CP-3**:
  - **FE-D**: tool return 不含 `function_call_output.files`，native 顯示 JSON-like text；vertical CSS scope style 該 text 為 placeholder + click handler
  - **FE-B**: 小 [core-touch] in `ToolCallDisplay.svelte` 加 Svelte context / event dispatch
  - **FE-C**: CSS hide + DOM mutation observer inject (brittle, last resort)
- **CP-2 影響**：無（adapter 不依賴此決定）
- **Will be promoted at CP-3 review**

#### P-005 — Data Analysis Chart Image Router Include
- **Status**: ✅ Active (approved CP-4)
- **File**: `backend/open_webui/main.py`
- **Lines**: +2 lines（router import + `app.include_router(...)`）
- **Commit prefix**: `[core-touch]`
- **First introduced**: 2026-05-11 (`d876d7e6a` — `[core-touch] feat: mount data analysis chart router`)
- **Why required**:
  FastAPI requires explicit router inclusion in `main.py`. Needed for serving
  dynamically generated chart PNGs from
  `/api/v1/data-analysis/charts/{chart_id}.png`.
- **Plan tier**: Plan C（confirmed CP-4 — no dynamic plugin router registration in current Open WebUI）
- **Approval**: 2026-05-11 by user / Tech Lead
- **Owner**: vertical/data-analysis backend
- **Related spec**: [`data-analysis-vertical-spec.md`](./spec/data-analysis-vertical-spec.md)、[`tools-schema.md`](./spec/tools-schema.md)
- **Removal condition**:
  Upstream adds dynamic router/plugin registration or a supported extension
  point for app-owned API routes → move router registration there and revert
  this `main.py` include.
- **Code snippet** (參考用，實際以 commit diff 為準):
  ```python
  from open_webui.routers import data_analysis
  app.include_router(data_analysis.router, prefix='/api/v1/data-analysis', tags=['data-analysis'])
  ```

#### P-006 — Data Analysis Event Worker Lifecycle Hook
- **Status**: ✅ Active (approved CP-5)
- **File**: `backend/open_webui/main.py`
- **Lines**: +4 lines（start worker during lifespan startup, stop/drain during shutdown）
- **Commit prefix**: `[core-touch]`
- **First introduced**: TBD（CP-5 implementation commit）
- **Why required**:
  Open WebUI has no generic worker plugin lifecycle. The data-analysis event
  ledger uses an async queue and background worker so analytics writes never
  block chat/tool execution, and the worker must be started/stopped inside the
  FastAPI lifespan for graceful shutdown.
- **Plan tier**: Plan C（tiny explicit lifecycle hook）
- **Approval**: 2026-05-12 by user / Tech Lead
- **Owner**: vertical/data-analysis backend
- **Related spec**: [`event-ledger.md`](./spec/event-ledger.md)
- **Removal condition**:
  Upstream adds a supported background-worker registration API → move
  `start_event_worker` / `stop_event_worker` there and revert this hook.

#### P-007 — Data Analysis Chat Delete Soft-Delete Hook
- **Status**: ✅ Active (approved CP-5)
- **File**: `backend/open_webui/models/chats.py`
- **Lines**: +6 lines across native chat delete paths
- **Commit prefix**: `[core-touch]`
- **First introduced**: TBD（CP-5 implementation commit）
- **Why required**:
  The event ledger intentionally preserves analytics history after UI chat
  deletion. Native chat delete paths must mark matching ledger rows
  `is_deleted = TRUE` / `deleted_at = ...` to avoid orphaned active analytics
  events while still retaining historical data.
- **Plan tier**: Plan C（tiny explicit delete hook; logic remains in `models/data_analysis_events.py`）
- **Approval**: 2026-05-12 by user / Tech Lead
- **Owner**: vertical/data-analysis backend
- **Related spec**: [`event-ledger.md`](./spec/event-ledger.md)
- **Removal condition**:
  Upstream adds a deletion lifecycle/hook mechanism for chat-owned extension
  data → register the ledger soft-delete there and revert this native model
  touch.

---

## Removed Patches（歷史紀錄）

> 此區記錄已 revert 的 patch（例如 upstream 自己提供等價 hook 後）。
>
> 格式：`#P-XXX — <name>`
>   - **Active 期間**: YYYY-MM-DD ~ YYYY-MM-DD
>   - **移除原因**: <upstream 加了 X，我們改用 native>
>   - **Revert commit**: <hash>

（目前無紀錄）

---

## Entry 範本（新增 patch 時複製此區塊）

```markdown
#### P-XXX — <Patch Name>
- **Status**: ✅ Active | ⏳ Pending | ❌ Removed
- **File**: `<path/to/file>`
- **Lines**: ~N lines
- **Commit prefix**: `[core-touch]`
- **First introduced**: YYYY-MM-DD (commit <hash>)
- **Why required**:
  <2–3 句說明：為什麼 native 不夠 / 為什麼不能用 Plan A>
- **Plan tier**: A / B / C
- **Owner**: <branch / team>
- **Related spec**: [`...`](...)
- **Removal condition**:
  <upstream 加了什麼 / 我們架構改了什麼，這個 patch 就可以移除>
- **Code snippet** (參考用):
  ```language
  ...
  ```
```

---

## Conflict Resolution Playbook

每次 rebase 衝突時遵循：

### 衝突類型 1：Hook 行範圍變動（最常見）
- **症狀**：upstream refactor 該檔，我們的 5 行 hook 出現在不同位置
- **處理**：
  1. 看 upstream diff，理解 refactor 的意圖
  2. 找 hook 對應的新位置（功能等價的地方）
  3. 把我們的 hook 搬過去
  4. 跑該檔的 test
  5. 更新此檔對應 entry 的 line range

### 衝突類型 2：Upstream 提供等價 hook
- **症狀**：upstream 加了 plugin API / slot / config extension，跟我們手刻的 hook 功能重疊
- **處理**：
  1. 比較 upstream 的 hook 與我們的差異
  2. 若功能等價 → revert 我們的 commit，改用 upstream 機制
  3. 此檔 entry 移到 Removed Patches，記錄移除原因
  4. Commit prefix `chore(upstream-sync): adopt upstream <hook> for P-XXX`

### 衝突類型 3：Upstream 改變了我們依賴的行為
- **症狀**：我們 hook 還在原處，但下游邏輯壞了（例：我們加進去的 entry 在原 sidebar 出現，但 click handler 邏輯被 upstream 改掉）
- **處理**：
  1. 暫停 rebase（`git rebase --abort` 退出）
  2. 在 entry 加 ⚠️ 標記
  3. 開 issue / 找 owner 討論 — 可能要重新評估 Plan A/B/C
  4. 處理完再 rebase

### 衝突類型 4：嚴重 conflict 解不掉
- **症狀**：upstream 大幅 refactor，我們的 hook 哲學跟 upstream 衝突
- **處理**：
  1. **不要強解**
  2. 暫停升級到 upstream 該版本
  3. 跟產品 / 工程主管討論：我們是否要 fork 得更深 / 改 architecture / 跳過此版
  4. 解決方案決定後再續

---

## 月度 review meeting agenda

每月 1 次（建議第一個週一），negotiate 30 分鐘：

1. Walk through Active Patches 列表，每個 entry：
   - 還需要嗎？
   - upstream 最近改動？
   - 行範圍對得上？
2. 列下個月 rebase 重點觀察項
3. 若有 ⚠️ 標記 entry → 排期解決
4. 議程結尾：所有 entry 都標 ✅ Confirmed (review date)

簡單但不能省。一次省略 = 兩個月後痛苦。
