# Merge plan: open-webui-custom ← open-webui/open-webui (2026-06)

**Goal**: bring our fork's `main` up to date with `upstream/main` cleanly,
keeping every `[core-touch]` patch (P-001..P-010) re-anchored to the new
upstream layout.

**Owner**: schedule as a single 1–2 day session — do not interleave with
other work. Each phase needs unbroken focus.

## Snapshot (captured 2026-06-14)

| | sha | one-line |
|---|---|---|
| our `main` | `be5c9695b` | Merge Stage 0-7: OWUI custom — Pi tool service, data analysis vertical, hub trace endpoints |
| `upstream/main` | `02dc3e689` | Merge pull request #25590 from open-webui/dev (2026-06-01) |
| merge-base | `f51d2b026` | Merge pull request #24483 from open-webui/dev (2026-05-09) |
| divergence | **+90 ours / +286 upstream** | 25 days behind |

Working branch: `feature/merge-upstream-2026-06` (already created, then
`git merge --abort`-ed; recreate from `main`).

## Conflict surface (already probed)

Dry-run merge produced **3 real conflicts** plus **6 auto-merges** (need
runtime smoke verification even if `git` reports clean):

| File | Status | Hunks | Patch IDs |
|---|---|---|---|
| `backend/open_webui/main.py` | UU (real) | 1 big block 472 lines | P-001, P-005, P-006 |
| `backend/open_webui/models/chats.py` | UU (real) | 3 places (3 delete methods) | P-007 |
| `backend/open_webui/utils/middleware.py` | UU (real) | 4 hunks | P-008 ("Phase 0 capture" + chat lifecycle events) |
| `src/lib/components/chat/Chat.svelte` | auto-merge | runtime check needed | P-003, P-009 |
| `src/lib/components/layout/Sidebar.svelte` | auto-merge | runtime check needed | P-002, P-010 |
| `src/lib/components/layout/Sidebar/ChatItem.svelte` | auto-merge | runtime check needed | P-008 |
| `backend/requirements.txt` | auto-merge | additive, low risk | new deps from our side |
| `pyproject.toml` | auto-merge | additive, low risk | new deps from our side |
| `static/pyodide/pyodide-lock.json` | auto-merge | take upstream wholesale | none |

## Re-anchor sheet (where each hook re-lands in upstream layout)

### `backend/open_webui/main.py` — take upstream, re-inject 4 hooks

upstream uses **lifespan-based** startup (`@asynccontextmanager`), not the
older `@app.on_event` we built on. Hooks move accordingly.

| Hook | Source commit | Old anchor | New anchor in upstream/main |
|---|---|---|---|
| Add `data_analysis,` to router imports | `d876d7e6a` | between `chats,` and `configs,` (line 481-511 block) | **line 487** — keep alphabetical, between `chats,` (487) and `configs,` (488) |
| `register_builtin_data_analysis_tool(app)` startup | `a608bb6d6` | post-tool-server-init | **line 734** — right after `set_terminal_servers` block, before `app.state.startup_complete = True` (line 736) |
| `start_event_worker(app)` startup | `b87b62e1d` | post-tool-registration | **line 735** — same block, after the tool registration above, still before `startup_complete = True` |
| `await stop_event_worker()` shutdown | `b87b62e1d` | shutdown handler | **line 743** — inside lifespan's `yield`/shutdown section, after `await close_session()` |
| `app.include_router(data_analysis.router, ...)` | `d876d7e6a` | router include block | **line 1432** — right after `chats.router` include (1431), before `notes.router` include (1432) to stay alphabetical |

**Resolution recipe**:
```bash
git merge --no-commit upstream/main
git checkout --theirs backend/open_webui/main.py
# then manually inject the 5 lines above
```

### `backend/open_webui/models/chats.py` — re-inject 3 ledger hooks

We added `DataAnalysisEvents.mark_deleted_safely` after each `delete(Chat)`
call. upstream renamed `db` → `session` in two of the three call sites but
kept the third as `db`.

| Hook | Source commit | New anchor in upstream/main |
|---|---|---|
| Hook 1: `delete_chat_by_id` | `b87b62e1d` | **line 1548** — after `await session.execute(delete(Chat).filter_by(id=id))`, before `return True and await self.delete_shared_chat_by_chat_id(...)`. Note **`db=session`** in the call (var was renamed). |
| Hook 2: `delete_chat_by_id_and_user_id` | `b87b62e1d` | **line 1560** — same pattern as above; `db=session`. |
| Hook 3: `delete_chats_by_user_id` | `b87b62e1d` | **line 1581** — call `DataAnalysisEvents.mark_deleted_by_user_id_safely(user_id=user_id, db=session)`. |

**There is also a 4th delete method now** (`delete_chats_by_user_id_and_folder_id`
at line 1588) that didn't exist when our patches were written. Decision
needed: do we want lifecycle event emission on folder-scoped delete too?
**Default: yes** — add the same hook there for consistency. Record the
addition as a new commit (not just rebase).

### `backend/open_webui/utils/middleware.py` — re-inject 4 hunks

| Hunk | Source commit | Old line | New anchor strategy |
|---|---|---|---|
| `response_started_at = time.perf_counter()` early init | `56df77fb1` (Phase 0 capture) | ~3389 | grep for `outlet_filter_handler(ctx)` function start; re-add the timer at top of `try` block |
| `schedule_chat_lifecycle_events(...)` for non-streaming | `7cdefd2d6` | ~3465 | grep for `non_streaming_chat_response_handler(response, ctx)` body, before final return |
| Same for streaming | `7cdefd2d6` | ~3567 | grep for `streaming_chat_response_handler(response, ctx)` body |
| Mid-stream early-return path | `7cdefd2d6` | ~5030 | grep for second instance of `streaming_chat_response_handler` further down |

upstream's file is now 5272 lines (we touched a 5048-line version). Each
hunk shifts by ~+30 lines. Use the function-name anchors above; never
re-apply by raw line number.

### Auto-merged but RUNTIME-VERIFY required

| File | What to verify |
|---|---|
| `Chat.svelte` | After OWUI starts, open a chat — does the data-analysis side panel still mount? Does `saveChatHandler` still write `request_prepared` metadata? |
| `Sidebar.svelte` | Does the "Data Analysis" vertical entry still appear in sidebar? |
| `ChatItem.svelte` | Does the lifecycle hook still fire on chat select? |
| `pyodide-lock.json` | `git checkout --theirs` — never our version |
| `requirements.txt`, `pyproject.toml` | confirm our deps survived the merge: `data-analysis` package, hub client. Run `pip install -e .` once. |

## Migration ordering

upstream added new alembic migrations (`3c9b0ca343fd_*`, `461111b60977_*`).
Our `e5f6a7b8c9d0_add_data_analysis_events.py` was previously the last;
after merge it may not be. **Check `alembic heads` returns a single head**;
if multi-head, write a merge migration.

## Pre-merge checklist (do these in this order)

1. **Save context**: re-read this doc + `docs/UPSTREAM_PATCHES.md`.
2. **Fetch fresh**: `git fetch upstream` again — there may be more commits since 2026-06-01.
3. **Update snapshot table** in this doc with fresh divergence numbers.
4. **Decide on the 4th delete method** in `chats.py` (see note above).
5. **Create branch**: `git checkout -b feature/merge-upstream-YYYY-MM main`.

## Execution flow

```
1. git merge --no-commit --no-ff upstream/main
2. # Resolve 3 conflicts using "take upstream + re-inject hooks" recipe above
3. git diff --check    # no whitespace conflict residue
4. # Static smoke:
   cd backend && PYTHONPATH=. python -c "from open_webui.main import app"
5. # Runtime smoke:
   cd backend && uvicorn open_webui.main:app --port 8080 &
   curl http://127.0.0.1:8080/health
   # Open browser, log in, open a chat in /workspace/data-analysis
6. # Test suite:
   <venv-python> -m pytest tests/data_analysis/ -q   # expect 75 passing
7. # Bridge e2e (need hub + this owui both running):
   cd ../pi-owui-bridge && AOH_PI_SHARED_SECRET=e2e-secret \
     AOH_OBSERVATION_DIR=~/.pi/observation \
     node e2e/run.mjs --mode=fake
   # expect 11/11
8. # Alembic check:
   cd backend && alembic heads   # expect single head
9. git commit -m "Merge upstream/main (YYYY-MM): re-anchor 5 hooks across main.py / chats.py / middleware.py per merge plan"
10. git checkout main && git merge --no-ff feature/merge-upstream-YYYY-MM
11. git push origin main
```

## Rollback

The merge is on its own branch, so abort/rollback is cheap:

```bash
git merge --abort                                 # mid-merge
git reset --hard main && git branch -D <branch>   # branch-level
```

## After merge: update UPSTREAM_PATCHES.md

Each P-NNN entry has a line-number anchor in its description. After
merge, walk through P-001..P-010 and update each anchor (and remove
any entry whose hook upstream now implements natively).

## Things we explicitly chose NOT to do here

- Touch `vendor` provider patches (Bedrock / Anthropic / Claude Fable
  / Moonshot etc.) — out of scope for OWUI merge. Those belong to pi merge.
- Drop the data-analysis vertical to slim the fork — not on the table.
- Switch to lifespan-based hooks before merge — would be a different patch.

## Why this is 1–2 days not 2–4 hours (revising earlier estimate)

The initial estimate counted conflict files (9), not their depth. The
main.py conflict is 472 lines spanning a full lifecycle reorganization;
each `[core-touch]` hook has to be re-validated against upstream's new
control flow, not just text-patched. The 3 svelte files report auto-merge
but svelte runtime behaviour is not statically checkable — we have to
actually open the UI. The 75 pytest tests need to pass on the merged
backend. Bridge e2e needs the merged owui process running.

Realistic budget:
- conflict resolution + static smoke: 3–4 hr
- runtime svelte verification + fixes: 2–3 hr
- pytest + fix any breakages: 2–4 hr
- bridge e2e + fixes: 1–2 hr
- UPSTREAM_PATCHES.md refresh: 1 hr
- buffer for surprises: 2–3 hr

= **1 calendar day if everything goes well, 2 if something needs
debugging**.
