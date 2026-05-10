# Project Guide — Brief / Contract Version

> **Quick reference of `PROJECT_GUIDE.md`. 修改本檔時必須同步更新 teaching 版。**

---

## Project

Vertical workspace built on top of Open WebUI fork.
- Repo: `https://github.com/istale/open-webui-custom`
- Branch: `vertical/data-analysis`
- Local: `/Users/istale/Documents/open-webui-based-project`
- Upstream: `https://github.com/open-webui/open-webui`

---

## Design Philosophy — Reuse-First

| ✅ DO | ❌ DON'T |
|---|---|
| Compose `Chat.svelte` into layout | Custom `MessageThread.svelte` |
| Express features as **tool calls** | Custom SSE event types |
| State in `chat.metadata.{namespace}` | Parallel `vertical_workspaces` table |
| `Depends(get_verified_user)` | Custom token fallback chains |
| Reuse `ContentRenderer` / `FollowUps` / `MessageInput` | Reimplement markdown / IME |
| Define `DatasetRepository` Port + Adapter | Scatter `httpx.get()` calls |

寫新 module 前先 grep Open WebUI ~80% 等價物。**Custom 是最後手段**。

---

## Reading Order (mandatory before code)

第一次讀 → teaching；之後查 → brief。

1. `docs/spec/PROJECT_GUIDE.md`
2. `docs/spec/openwebui-module-inventory.md` — Tier 1/2/3 reuse 清單
3. `docs/spec/tools-schema.md` — vertical features as native tool calls
4. `docs/spec/database-adapter.md` — Port-and-Adapter
5. `docs/spec/data-analysis-vertical-spec.md` — manufacturing UX + chart types
6. `docs/spec/frontend-spec.md` — frontend contracts
7. `docs/spec/frontend-design-tokens.md` — visual design system
8. `docs/spec/event-ledger.md` — analytics events table
9. `docs/design/mockup-analysis.md` — design mockup mapping

---

## Day 0 Initial Commit Structure

```
{repo}/
├── .gitignore
├── .pre-commit-config.yaml
├── README.md / AGENTS.md
├── docs/
│   ├── spec/
│   │   ├── README.md
│   │   ├── *.md (teaching)
│   │   └── *.brief.md (contract)
│   └── design/
│       ├── 3panel-mockup.html
│       └── mockup-analysis.md
├── backend/open_webui/
│   ├── routers/data_analysis.py
│   ├── tools/data_analysis/
│   ├── utils/data_analysis/
│   ├── models/data_analysis_events.py
│   └── migrations/versions/<n>_add_data_analysis_events.py
├── src/
│   ├── routes/(app)/workspace/data-analysis/
│   └── lib/components/data-analysis/
└── tests/data_analysis/
```

Tier 3 hard cap: **15 frontend files + minimal backend**。

---

## Week 1 Path

| Day | Goal | Tag |
|---|---|---|
| 0 | Repo + spec docs committed | `bootstrap-day-0` |
| 1 | Open WebUI inventory complete | `inventory-done` |
| 2 | Vertical UX spec written | — |
| 3 | DatasetRepository Port + InMemory adapter + fixtures | — |
| 4 | First tool: `list_datasets` end-to-end | — |
| 5 | `query_dataset` + `render_chart` + image endpoint | `tools-done` |
| 6 | Three-panel + canvas feed + scroll | `mvp-frontend` |
| 7 | RBAC + persistence + ledger emit | `mvp-day-7` |

---

## Hard Rules

1. **Reuse-First**: grep before writing
2. No custom SSE events → tool calls
3. State in `message.metadata.{namespace}` 或 ledger
4. No `import httpx` in tool / route → adapter only
5. `schema_version: 1` from day 0 on all persisted shapes
6. LLM never outputs infrastructure fields (id / timestamps / cache keys)
7. Backend `uuid4().hex` for all chart IDs
8. **WIP commits hourly** — untracked files vanish silently
9. Tag milestones (`bootstrap-day-0`, `inventory-done`, etc.)
10. **Stop before core touch**：改 `Chat.svelte` / core router 必須 `[core-touch]` prefix + 問 user
   - Pre-approved core touch: 1 行 startup hook in `main.py` for tool registration

## Core Touch Discipline

- **最小化接觸面積**：native 留 hook（slot / extension store），邏輯在 vertical
- **每處 hook ≤ 5 行**
- **記錄 `docs/UPSTREAM_PATCHES.md`**：檔案 / 行範圍 / 為什麼必須改 / Plan A/B/C
- **Pre-approved core touches 清單**：只有 `main.py` 的 startup hook
- **Rebase upstream 月檢查**：用 `UPSTREAM_PATCHES.md` 為 checklist 走過所有 patches

詳見 [`PROJECT_GUIDE.md` Core Touch Discipline](./PROJECT_GUIDE.md#core-touch-discipline-fork-維護關鍵)。

---

## Pre-commit Anti-pattern Checklist

每次 commit 前自查：
- [ ] 沒建 `*Thread.svelte` / `*Messages.svelte`
- [ ] 沒定義 custom SSE event types
- [ ] 沒建 parallel message structure
- [ ] 沒把 vertical state 放 `chat.metadata` 外（除 ledger）
- [ ] tool / route code 內無 `import httpx`
- [ ] LLM 不期望輸出 infrastructure 欄位
- [ ] 沒漏寫 InMemory adapter
- [ ] vertical UI 元件 ≤ 15 個

---

## Repo Conventions

- Branch：`vertical/{name}` for vertical, `feature/{name}` for cross-cutting
- Commits：imperative，type prefix (`spec:`, `feat:`, `fix:`, `chore:`, `test:`, `docs:`, `design:`)
- Spec changes：每次 spec 改動單獨 commit（`git blame` 看設計決策）
- Tool changes：persisted schema 改動 → bump `schema_version`

---

## Spec Versioning

每份 spec 維護 `<name>.md` (teaching) 與 `<name>.brief.md` (contract) 兩版。
**改 spec 兩版必同 commit**。詳見 [`docs/spec/README.md`](./README.md)。
