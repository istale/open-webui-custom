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

- Chart types `line / scatter / heatmap / spc / pareto / histogram` are covered by
  unit tests but not yet exercised in live browser QA (control / box / bar were).
- Branch / regenerate behavior in the workspace not yet live-tested.
