# Vertical Workspace Project — Day 0 Bootstrap

> ⚡ **Quick reference**: [`PROJECT_GUIDE.brief.md`](./PROJECT_GUIDE.brief.md) — 純契約。**修改本檔時必須同步更新 brief 版**。
>
> **複製到新 repo 的 README.md 起手式。包含：reuse-first 哲學、初始 commit 結構、第一週路徑。**

---

## What this is

A **vertical-domain workspace** built natively on top of [Open WebUI](https://github.com/open-webui/open-webui). Reuses Open WebUI's chat lifecycle, message tree, history persistence, and RBAC instead of duplicating them.

**Vertical example**: Manufacturing data analysis — three-panel layout (dataset / canvas / chat), domain-specific charts (control / SPC / Pareto), connected to an external standalone manufacturing data system via a database adapter.

---

## Design Philosophy — Reuse-First

| ✅ DO | ❌ DON'T |
|---|---|
| Compose `Chat.svelte` into your layout | Write a custom `MessageThread.svelte` |
| Express vertical features as **tool calls** | Define custom SSE event types |
| Store vertical state in `chat.metadata.{namespace}` | Build a parallel `vertical_workspaces` DB table |
| Use `Depends(get_verified_user)` | Implement custom token fallback chains |
| Borrow `ContentRenderer` / `FollowUps` / `MessageInput` | Reimplement markdown / code highlight / IME |
| Define a `DatasetRepository` Port and inject Adapter | Scatter `httpx.get(EXTERNAL_API_URL)` calls |

> **Rule of thumb**: before writing any new module, grep Open WebUI for ~80% existing equivalents. Custom is the last resort, not the first.

---

## Reading order (mandatory before coding)

1. [`docs/spec/openwebui-module-inventory.md`](./openwebui-module-inventory.md) — Tier 1/2/3 modules to reuse
2. [`docs/spec/tools-schema.md`](./tools-schema.md) — express vertical features as native tool calls
3. [`docs/spec/database-adapter.md`](./database-adapter.md) — port-and-adapter for external data system
4. [`docs/spec/{vertical}-spec.md`](./) — vertical-specific UX / persistence spec (write this first thing)

---

## Day 0 — Initial Commit Structure

Before writing any code, set up this skeleton and commit it:

```
{new-repo}/
├── .gitignore                     # standard + .env + data/cache/
├── .pre-commit-config.yaml        # warns on >2hr untracked files
├── README.md                      # this file (adapted)
├── docs/
│   └── spec/
│       ├── openwebui-module-inventory.md   # copy from this folder
│       ├── tools-schema.md                 # copy from this folder
│       ├── database-adapter.md             # copy from this folder
│       └── {vertical}-spec.md              # write Day 1
├── backend/
│   └── open_webui/                # cloned from open-webui upstream
│       ├── routers/
│       │   └── {vertical}.py      # vertical-specific endpoints (thin)
│       ├── tools/
│       │   └── {vertical}/        # tool implementations
│       │       ├── __init__.py
│       │       ├── query_dataset.py
│       │       ├── render_chart.py
│       │       └── ...
│       └── utils/
│           └── {vertical}/
│               ├── __init__.py
│               ├── repository.py        # Port (DatasetRepository Protocol)
│               ├── adapters/
│               │   ├── http_adapter.py
│               │   └── in_memory_adapter.py
│               ├── chart_renderer.py    # matplotlib pipeline
│               └── fixtures.py          # InMemory test data
├── src/
│   ├── routes/(app)/{vertical}/+page.svelte    # 3-panel shell
│   └── lib/
│       └── components/
│           └── {vertical}/                     # custom UI bits ONLY
│               ├── DatasetPanel.svelte
│               └── CanvasFeed.svelte
└── tests/
    └── {vertical}/
        ├── test_repository_contract.py
        ├── test_tools.py
        └── ...
```

**Note**: `src/lib/components/{vertical}/` should have **at most 5–8 files**. If you're approaching that, you're over-building — go back to inventory and reuse more.

---

## Day 0 — First Commit Sequence

```bash
# 1. Init from open-webui upstream
git clone https://github.com/open-webui/open-webui.git {new-repo}
cd {new-repo}
git checkout -b vertical/{vertical-name}

# 2. Drop in the spec docs (copy from old project)
mkdir -p docs/spec
cp ../old-project/docs/spec/openwebui-module-inventory.md docs/spec/
cp ../old-project/docs/spec/tools-schema.md docs/spec/
cp ../old-project/docs/spec/database-adapter.md docs/spec/
cp ../old-project/docs/spec/NEW_REPO_README.md docs/spec/

# 3. First commit — spec only, no code yet
git add docs/spec/
git commit -m "spec: vertical workspace design docs (inventory + tools + db-adapter)"

# 4. Set up .gitignore + pre-commit
cat >> .gitignore <<EOF

# Vertical workspace
data/cache/
.env.local
*.pyc
__pycache__/
EOF

git add .gitignore && git commit -m "chore: gitignore vertical cache + env"

# 5. Tag the bootstrap point
git tag bootstrap-day-0
```

---

## Week 1 — Path

每個 Day 結束的 tag 對應一個 **review checkpoint**，agent 必須停下等 user APPROVED 才繼續（詳見 [`docs/review-protocol.md`](../review-protocol.md)）。

| Day | Goal | Tag | Checkpoint |
|---|---|---|---|
| 0 | Repo skeleton + spec docs committed | `bootstrap-day-0` | (initial state) |
| 1 | **Inventory** — read Tier 1 modules, fill `inventory-results.md`, decide Plan A/B/C × 3 | `inventory-done` | **CP-1** |
| 2–3 | Define Port + InMemory + HTTP adapters + fault injection + tests | `adapter-done` | **CP-2** |
| 4 | First tool E2E: `list_datasets` callable from native chat | `first-tool-e2e` | **CP-3** |
| 5 | Remaining tools: `query_dataset` + `render_chart` (9 chart types) + summarize / get_schema + image endpoint | `tools-done` | **CP-4** |
| 5 | Event ledger: DB migration + worker + 12 P0 events emit | `ledger-done` | **CP-5** |
| 6 | Three-panel shell + canvas feed + native chat integration + auto-scroll + sidebar entry | `mvp-frontend` | **CP-6** |
| 7 | RBAC + persistence + acceptance criteria 全綠 | `mvp-day-7` | **CP-7** |

After Week 1: switch InMemory adapter to HTTP adapter against staging external system.

> Day 5 同時包 tools-done 跟 ledger-done — 看實作順序，建議先 tools 再 ledger（ledger 整合需要 tool 已 emit）。

---

## Core Touch Discipline (Fork 維護關鍵)

> **背景**：Open WebUI 是快速迭代的開源專案。每次 `git rebase upstream/main` 拉新版時，我們的 `[core-touch]` 修改會跟 upstream 衝突。**修改愈多 / 散落愈廣 = 衝突愈痛**。本節是 fork 長期維護的紀律守則。

### 原則 1：最小化接觸面積

當 inventory 結果指出某個 native 檔案必須改（例：sidebar 不支援動態 entry，得改 `Sidebar.svelte`），**絕對不要把長串判斷邏輯寫進 native 檔案**：

❌ **錯誤作法**（散布 vertical 邏輯到 native 檔）：
```svelte
<!-- Sidebar.svelte -->
<script>
    {#if workspace_type === 'data-analysis'}
        <DataAnalysisFilter />
        <DataAnalysisHistoryList />
        <DataAnalysisNewButton />
    {/if}
    {#if workspace_type === 'finance'}  <!-- 未來 vertical -->
        ...
    {/if}
</script>
```
這樣每加一個 vertical 就改 native 一次。Rebase 衝突指數成長。

✅ **正確作法**（native 留 hook，邏輯在 vertical）：
```svelte
<!-- Sidebar.svelte：加一個 slot 或 store-driven extension point -->
<aside>
    <!-- ... 原生內容 ... -->
    {#each $sidebarExtensions as ext}
        <svelte:component this={ext.component} />
    {/each}
</aside>
```
```ts
// vertical 自己 register（不動 native 檔案）
// src/lib/components/data-analysis/sidebar-extension.ts
import { sidebarExtensions } from '$lib/stores/sidebar';
import DataAnalysisEntry from './DataAnalysisEntry.svelte';

sidebarExtensions.update((arr) => [...arr, { id: 'da', component: DataAnalysisEntry }]);
```

Native 改動 = **1 次（加 hook）**。之後加 N 個 vertical 都不再動 native。

### 原則 2：Hook 寬度 ≤ 5 行

每處 `[core-touch]` 修改的 native 程式碼**不可超過 5 行**。如果你發現要改 20 行，幾乎一定可以重構成「在 native 加 1 行 hook + vertical 內 19 行 implementation」。

### 原則 3：每個 [core-touch] commit 必須記錄到 `docs/UPSTREAM_PATCHES.md`

- 修改的檔案
- 修改的具體行範圍
- **為什麼必須改**（無法用其他 plan 的原因）
- Plan A/B/C 哪個 fallback
- 對應的 spec 文件

範本見 [`docs/UPSTREAM_PATCHES.md`](../UPSTREAM_PATCHES.md)。

### 原則 4：Rebase upstream 時優先檢查

每月 `git fetch upstream && git rebase upstream/main` 時：

```bash
# 列出所有 [core-touch] commits
git log --oneline | grep '\[core-touch\]'

# 對每個 commit 確認：
#  1. 修改的檔案 upstream 最近有沒有改動？
#  2. 我們的 hook 還在原處嗎？
#  3. 有沒有 conflict？
```

`UPSTREAM_PATCHES.md` 是這個 review 的 checklist source。如果你 rebase 時發現某個 patch 已不需要（upstream 自己加了 hook 機制），standard procedure：
1. Revert 那個 commit
2. 把 vertical 改用 upstream 的新 hook
3. 從 `UPSTREAM_PATCHES.md` 移除該紀錄
4. Commit message 標 `chore(upstream-sync): ...`

### 原則 5：Pre-approved Core Touches 清單

唯一不需另外 approval 的 core touch（per `tools-schema.md`）：

| 檔案 | 變動 | 用途 |
|---|---|---|
| `backend/open_webui/main.py` | +5 lines `@app.on_event('startup')` | 註冊 vertical built-in tool |

其他**任何** core touch 必須：
1. Commit prefix `[core-touch]`
2. 記入 `UPSTREAM_PATCHES.md`
3. 與 user 確認 Plan A 真的不可行

---

## Anti-pattern checklist (run before each commit)

Before pushing, check that you haven't done any of these:

- [ ] Created a `*Thread.svelte` / `*Messages.svelte` instead of using `Chat.svelte`
- [ ] Defined custom SSE event types (`event: plan` / `event: card`)
- [ ] Built a parallel message structure (custom `messages: ChatMessage[]`)
- [ ] Stored vertical state outside `chat.metadata.{namespace}`
- [ ] Wrote `import httpx` in tool / route code (should be in adapter only)
- [ ] LLM expected to output infrastructure fields (id / timestamps / cache keys)
- [ ] Skipped writing the InMemory adapter (only HTTP adapter)
- [ ] More than 8 custom Svelte components for the vertical UI

If any of these are true, stop and reconsider — you're recreating last project's mistakes.

---

## Lessons learned from the previous attempt (reference)

The previous data-analysis project went through 8 architectural pivots in 5 days because we built custom modules first, then spent Phase 3 retrofitting native integration. Key takeaways:

1. **Server-side vs client-side rendering is domain-dependent** (manufacturing forensics → server-side matplotlib + spec; SaaS exploration → client Chart.js).
2. **Schema versioning from day 0** is mandatory — `schema_version: 1` on every persisted shape.
3. **Three-layer schema discipline** — LLM output ≠ Backend enrichment ≠ Persistence. Don't share types across layers.
4. **Single source of truth fights** — every duplicated state will cause sync bugs within 3 months. Pick one, derive the rest.
5. **WIP commits save you** — untracked files vanish silently from `git clean` / IDE / agent operations. Commit hourly even for WIP.
6. **Native chat lifecycle covers more than you think** — branching, regenerate, persistence, RBAC, follow-ups are all already there.

For full context, see [the historical migration plan](../data-analysis-native-lifecycle-migration-plan.md) — but treat it as **what NOT to repeat**, not as a guide.

---

## Repo conventions

- **Branch naming**: `vertical/{name}` for the vertical workspace, `feature/{name}` for cross-cutting changes
- **Commits**: imperative mood, prefix with type (`spec:`, `feat:`, `fix:`, `chore:`, `test:`, `docs:`)
- **Spec changes**: every spec change = a commit on its own (so you can `git blame` design decisions)
- **Tool changes**: tool schema changes require a `schema_version` bump if persisted
