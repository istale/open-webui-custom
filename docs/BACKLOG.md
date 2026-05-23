# Backlog — Data Analysis Vertical

Non-blocking items deferred from live QA / review. Each entry: what, why deferred, where.

---

## UX / Frontend

- **Sidebar chat item middle-click / cmd-click opens plain chat view**
  `src/lib/components/layout/Sidebar/ChatItem.svelte` — the click handler routes
  data-analysis chats correctly via `getChatHref()` (`/workspace/data-analysis/{id}`),
  but the static `<a href="/c/{id}">` (line ~463) is used by middle-click /
  cmd-click / "open in new tab", so those land on the plain chat view instead of
  the workspace. Fix needs the href to be metadata-aware, which requires async
  chat load before render. Low impact (left-click works). Deferred 2026-05-23.

## Analytics / Event ledger

- **`chart.rendered` denormalized `chat_id` is null for first chart in a new chat**
  When a chart is created on the new-chat route (`/workspace/data-analysis`, before
  the URL gains its id), the frontend `chart.rendered` event is logged with
  `chat_id = null`. The `chart_id` is still in `payload`, so analytics can join via
  the backend `tool.render_chart.succeeded` event. Fix: read the assigned chat id
  (from URL after replaceState) at dispatch time. Low impact. Deferred 2026-05-23.

## Verification gaps (low risk)

- Chart types `scatter / heatmap / pareto / histogram` are covered by unit tests
  but not yet exercised in live browser QA. Live-verified so far: control, box,
  bar, line, spc. (The frontend path is identical for all types — only the
  matplotlib rendering differs, which the unit tests cover.)
- ~~Branch / regenerate behavior~~ — live-verified 2026-05-24: regenerating creates
  a new sibling branch with its own chart; the canvas tracks the active branch via
  `createMessagesList(history, currentId)` and shows exactly one chart, swapping
  correctly when navigating siblings (no duplication or leak).
