# Vertical Workspace Project — Day 0 Bootstrap

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

| Day | Goal | Deliverable |
|---|---|---|
| 0 | Repo skeleton + spec docs committed | `bootstrap-day-0` tag |
| 1 | **Inventory** — read Tier 1 modules, fill in inventory checklist | Updated `openwebui-module-inventory.md` |
| 2 | Vertical spec — three-panel UX, persistence strategy, auth model | `docs/spec/{vertical}-spec.md` |
| 3 | Define Port + InMemory adapter + fixtures | `repository.py` + `in_memory_adapter.py` + fixtures |
| 4 | First tool: `list_datasets` end-to-end via native chat | LLM can list datasets via tool call |
| 5 | Tool: `query_dataset` + `render_chart` | LLM can produce a chart attachment |
| 6 | Three-panel shell + canvas feed (derived from `message.toolCalls[]`) | Visible vertical workspace |
| 7 | RBAC verification + persistence smoke test (reload, branch, regenerate) | Shippable MVP |

After Week 1: switch InMemory adapter to HTTP adapter against staging external system.

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
