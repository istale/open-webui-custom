# AGENTS.md — Mission Brief for Code Agents

> **Read this first.** Then read `docs/spec/PROJECT_GUIDE.md` and the four spec docs in `docs/spec/`.

## Mission

Build a **data analysis vertical workspace** as a feature branch on a fork of Open WebUI. Reuse Open WebUI's chat lifecycle, message tree, history, RBAC. Add only what's vertical-specific.

## Spec Reading Posture（重要）

The team that owns this project has **limited frontend/backend experience and is
encountering Open WebUI for the first time**. Spec docs in `docs/spec/` are
written as **teaching documents**, not minimalist contracts:

- They explain **what** + **why** + **how** (concept → reasoning → step-by-step)
- They include diagrams, tables, code snippets, and walkthroughs
- They label anti-patterns explicitly
- They cross-reference each other liberally

**Do not skim**. The redundancy is intentional — if you skip the "why" sections
and only read the contracts, you'll make the same mistakes the previous attempt
made (custom modules, parallel state, ignored native lifecycle).

Likewise, **when you write code** that the team will read:
- Comment the **non-obvious why**, not the obvious what
- Match the spec's level of detail in PR descriptions
- Don't assume the reader knows SvelteKit / FastAPI / Open WebUI — link spec
  sections that explain the concept

This applies to all spec updates you make. Match the existing style:
concept → diagram → table → step-by-step → code → anti-patterns.

## Repo Topology

- **Fork**: `https://github.com/istale/open-webui-custom`
- **Local working tree**: `/Users/istale/Documents/open-webui-based-project`
- **Default branch**: `main` (mirrors `upstream/main`, never write here)
- **Working branch**: `vertical/data-analysis` (do all work here)
- **Upstream remote**: `https://github.com/open-webui/open-webui` (for periodic sync)

## Reading Order (mandatory before writing code)

1. `docs/spec/PROJECT_GUIDE.md` — overall philosophy & day-by-day plan
2. `docs/spec/openwebui-module-inventory.md` — what to reuse from Open WebUI (Tier 1/2/3)
3. `docs/spec/tools-schema.md` — vertical features expressed as native tool calls
4. `docs/spec/database-adapter.md` — Port-and-Adapter for external standalone data system
5. `docs/spec/data-analysis-vertical-spec.md` — vertical-specific UX, persistence, chart types
6. `docs/spec/frontend-spec.md` — frontend contracts (component props, stores, event flow, auto-scroll, native Chat integration plans A/B/C)
7. `docs/spec/frontend-design-tokens.md` — visual design system (colors, fonts, radius, shadow, transition, interaction patterns)
8. `docs/design/mockup-analysis.md` — analysis of user-designed 3panel-mockup.html and component mapping

## Hard Rules (non-negotiable)

1. **Reuse-First**: Before creating any new module, grep Open WebUI codebase for an equivalent. If found, use it. Custom is the last resort.
2. **No custom SSE event types** — vertical functionality goes through native tool calling (`message.toolCalls[]`).
3. **No parallel message structures** — store vertical state in `message.metadata.{namespace}` or `chat.chat.metadata.{namespace}`.
4. **No `import httpx` in tool / route code** — that goes only inside `utils/data_analysis/adapters/`.
5. **Schema versioning from day 0** — every persisted shape carries `schema_version: 1`.
6. **LLM never outputs infrastructure fields** — no `id`, no timestamps, no cache keys. Tool function `parameters` schema enforces this.
7. **Backend always generates `uuid4().hex` for chart IDs** — never `f'card-{index}'`.
8. **WIP commits hourly** — untracked files are fragile (lesson from previous attempt). Commit even half-done work to `vertical/data-analysis`.
9. **Tag milestone points** — `bootstrap-day-0`, `inventory-done`, `first-tool-working`, etc.
10. **Stop before touching core files** — if you must modify `Chat.svelte` / core router / etc., flag it in commit message with `[core-touch]` and ask the user first.

## Anti-patterns (strictly avoid)

These were all done in the previous attempt and led to 5 days of recovery work:

- ❌ Custom `MessageThread.svelte` — use `Chat.svelte` + native `Messages.svelte`
- ❌ Custom `streamDataAnalysis.ts` — native tool calling has streaming built in
- ❌ Custom `event: plan` / `event: card` SSE — express as tool calls
- ❌ Custom `metadata.thinking_content` — use native `<think>` in content
- ❌ Page-level `resultCards: ResultCard[]` array — derive from `message.toolCalls[]`
- ❌ Custom token fallback chains — use `Depends(get_verified_user)`
- ❌ Direct DB calls or HTTP calls in tools — go through `DatasetRepository` Port

## Workflow

```bash
# Always work on the vertical branch
cd /Users/istale/Documents/open-webui-based-project
git checkout vertical/data-analysis

# Hourly WIP commits
git add -A && git commit -m "wip: <what you just did>"

# Periodic upstream sync (weekly)
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
git checkout vertical/data-analysis
git rebase main   # or merge, depending on team preference
```

## How to ask the user before doing risky things

Always pause and confirm before:
- Modifying any file outside the vertical-specific paths (see PROJECT_GUIDE.md)
- Adding a new top-level dependency (`package.json`, `requirements.txt`)
- Writing schemas / types that span multiple Layer 1/2/3 boundaries
- Skipping a Tier 1 module from inventory and writing custom

## Definition of Done — Day 7 MVP

- [ ] All 4 spec docs read and inventory checklist filled
- [ ] `DatasetRepository` Port + InMemory adapter + fixtures usable in tests
- [ ] `list_datasets` / `query_dataset` / `render_chart` tools registered and callable from native chat
- [ ] Three-panel layout at `/data-analysis` route, native `Chat.svelte` on right panel
- [ ] Canvas feed derived from `message.toolCalls[]`, auto-scrolls correctly
- [ ] Reload survives — charts re-render from cached PNG (or regen)
- [ ] At least one happy-path manual QA recording
- [ ] All work committed and pushed to `origin/vertical/data-analysis`
