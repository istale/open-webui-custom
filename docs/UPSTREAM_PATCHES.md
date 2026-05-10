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
- **First introduced**: TBD（Day 5–6 工程實作時加上）
- **Why required**:
  Open WebUI 沒有 tool plugin / dynamic registration API。Tools 必須存在 DB 表中。
  最乾淨方式：startup hook 把我們 vertical 自帶的 `class Tools` 寫進 DB
  並 warm `app.state.TOOLS` cache。詳見 [`tools-schema.md` 「整合 Open WebUI 的 Tool Registration」](./spec/tools-schema.md#整合-open-webui-的-tool-registration已實際確認)。
- **Plan tier**: Plan B（無 native hook，但寬度極小）
- **Owner**: vertical/data-analysis backend
- **Related spec**: [`tools-schema.md`](./spec/tools-schema.md)、[`tools-schema.brief.md`](./spec/tools-schema.brief.md)
- **Removal condition**:
  Upstream 加了 `register_builtin_tool(...)` API → 改用 native API + revert 此 hook
- **Code snippet** (參考用，實際以 commit diff 為準):
  ```python
  @app.on_event("startup")
  async def _seed_vertical_tools():
      """[core-touch] Vertical workspace tool registration."""
      from open_webui.tools.data_analysis import register_builtin_data_analysis_tool
      await register_builtin_data_analysis_tool(app)
  ```
- **Upstream interaction notes** (post-sync 2026-05-09 to `f51d2b026`):
  - Upstream 加了 `app.state.TOOL_CONTENTS = {}` (`main.py:983`) +
    cache invalidation logic (`utils/tools.py:194-198`)
  - 我們的 `register_builtin_data_analysis_tool` 必須**同時**設
    `app.state.TOOL_CONTENTS[BUILTIN_TOOL_ID] = content`，否則第一次
    tool resolution 時會把 live instance 替換成 DB-exec 出來的
  - 此調整已寫入 [`tools-schema.md`](./spec/tools-schema.md)
    與 [`tools-schema.brief.md`](./spec/tools-schema.brief.md)

---

### Inventory-driven (Day 1 結果決定)

依 Day 1 inventory 結果（[`inventory-results.md`](./spec/inventory-results.md)），以下三個 patch **可能需要**。實作時填入細節並 promote 到 Active Patches 區。

#### P-002 — Sidebar Entry for Vertical Workspace
- **Status**: ⏳ Pending Day 1 inventory
- **File**: `src/lib/components/layout/Sidebar.svelte`（如果 Plan C）
- **Decision**: Plan A / B / C — 未定
  - Plan A: 原生支援 dynamic registration → **0 core touch**，移除此 entry
  - Plan B: config 擴展 → 改 config 檔案，仍記錄此 entry
  - Plan C: hard-code → 動 `Sidebar.svelte`，記錄此 entry
- **If Plan C, intended hook**:
  - 加 1 個 NavItem (5 行內)
  - 連到 `/workspace/data-analysis`
  - icon `📊` + label `Data Analysis`
- **Why required**: Sidebar 是進入 vertical workspace 的入口
- **Related spec**: [`frontend-spec.md` §1.4](./spec/frontend-spec.md#14-sidebar-entry--怎麼加-data-analysis-入口)
- **Owner**: TBD

#### P-003 — Sidebar Vertical Chat Differentiator
- **Status**: ⏳ Pending Day 1 inventory
- **File**: `src/lib/components/layout/Sidebar.svelte`（如果 Plan C）
- **Decision**: 是否要在 chat list 區分 vertical vs generic chat
  - Plan A: native sidebar 支援 plugin / icon override → **0 core touch**
  - Plan B/C: 改 native click handler 偵測 `metadata.workspace_type` 切路徑
- **If Plan C, intended hook**:
  ```ts
  const isVertical = chat?.chat?.metadata?.workspace_type === 'data-analysis';
  if (isVertical) goto(`/workspace/data-analysis/${chat.id}`);
  else goto(`/c/${chat.id}`);
  ```
- **Why required**: 點擊 vertical chat 必須路由到 `/workspace/data-analysis/{id}`
- **Related spec**: [`frontend-spec.md` §1.7](./spec/frontend-spec.md#17-vertical-chat-vs-generic-chat-在-sidebar-怎麼分)
- **Owner**: TBD

#### P-004 — ResponseMessage Image Render Hook (`<ChatPlaceholder>`)
- **Status**: ⏳ Pending Day 1 inventory
- **File**: `src/lib/components/chat/Messages/ResponseMessage.svelte`（如果 Path FE-C）
- **Decision**: Path FE-A / FE-B / FE-C — 未定
  - Path FE-A: 原生支援 tool-call file/result render hook（例如 `files[].metadata.render_mode`）→ **0 core touch**
  - Path FE-B: wrap / context cascade → 0 core touch（在 vertical 內處理）
  - Path FE-C: native ResponseMessage hard-code 圖片渲染 → conditional patch
- **If Path FE-C, intended hook**:
  ```svelte
  {#if attachment.type === 'image' && $vertical?.placeholderRender}
      <svelte:component this={$vertical.placeholderRender} {attachment} />
  {:else}
      <img src={attachment.url} ... />  <!-- native original -->
  {/if}
  ```
- **Why required**: 在右欄 chat 內把 chart attachment 渲染成 small placeholder（「📊 已加到分析畫布」）而非完整大圖
- **Related spec**: [`frontend-spec.md` §6](./spec/frontend-spec.md#6-native-chat-extension-hooks-placeholder--caption)
- **Owner**: TBD

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
