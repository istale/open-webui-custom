# Event Ledger — Brief / Contract Version

> **Quick reference of `event-ledger.md`. 修改本檔時必須同步更新 teaching 版。**

---

## Two-tier persistence

| Layer | Where | Purpose |
|---|---|---|
| Live state | `chat.chat.metadata` | UI render / reload (sync, OLTP) |
| Analytics ledger | `data_analysis_events` table | Behavioral analytics / ML (async, OLAP) |

Ledger 是**附加**，不取代 chat metadata。

---

## Schema

```sql
CREATE TABLE data_analysis_events (
    id            TEXT PRIMARY KEY,            -- uuid4
    ts            BIGINT NOT NULL,             -- ms
    user_id       TEXT NOT NULL,
    user_org_id   TEXT,                        -- 預留 multi-tenant
    chat_id       TEXT,
    message_id    TEXT,
    workspace     TEXT NOT NULL DEFAULT 'data-analysis',
    event_type    TEXT NOT NULL,
    schema_version INT NOT NULL DEFAULT 1,
    payload       JSONB NOT NULL,
    -- denormalized
    dataset_id    TEXT,
    chart_type    TEXT,
    tool_name     TEXT,
    duration_ms   INT,
    success       BOOLEAN NOT NULL DEFAULT TRUE,
    error_code    TEXT,
    -- soft delete
    is_deleted    BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at    BIGINT
);

-- Indexes
(user_id, ts)
(chat_id, ts) WHERE is_deleted = FALSE
(event_type, ts)
(dataset_id, ts) WHERE dataset_id IS NOT NULL
(chart_type, ts) WHERE chart_type IS NOT NULL
(success, ts)
```

---

## P0 Events (12)

| event_type | payload 必填 | Emit 點 |
|---|---|---|
| `workspace.opened` | `entry_path` | Frontend `+layout.svelte` mount |
| `dataset.selected` | `dataset_id`, `prev_dataset_id`, `from` | Frontend DatasetPanel |
| `prompt.submitted` | `prompt_text`, `prompt_length`, `model`, `is_first_in_chat` | Frontend on Send |
| `model.thinking_completed` | `thinking_text`, `n_chars`, `duration_ms` | Backend chat completion forwarder（vertical-only Plan B）|
| `tool.query_dataset.succeeded` | `sql`, `query_id`, `row_count`, `truncated`, `duration_ms` | Backend `query_dataset` return |
| `tool.query_dataset.failed` | `sql`, `error_code`, `error_message`, `duration_ms` | Backend `query_dataset` except |
| `tool.render_chart.succeeded` | `chart_type`, `query_id`, `chart_id`, `image_size_bytes`, `duration_ms`, `statistics` | Backend `render_chart` return |
| `tool.render_chart.failed` | `chart_type`, `error_code`, `error_message`, `duration_ms` | Backend `render_chart` except |
| `chart.rendered` | `chart_id`, `chart_type`, `displayed_in` | Frontend canvas card mount |
| `message.assistant_completed` | `message_id`, `total_duration_ms`, `tool_call_count`, `n_chars`, `had_thinking` | Backend / native message done hook |
| `stream.timeout` | `chat_id`, `elapsed_ms`, `last_event_type` | Frontend `streamDataAnalysis` timeout catch |
| `stream.aborted` | `chat_id`, `reason` | Frontend abort handler |
| `followup.clicked` | `followup_text`, `source_message_id`, `followup_index` | Frontend FollowUps click |

## Backlog

`chart.viewed` / `chart.locate_clicked` / `message.thumbs_up` / `message.thumbs_down` / `chart.image_load_error` / `dataset.access_denied`

## Naming convention

`<area>.<action>[.<outcome>]`

---

## Emit API

```python
# backend/open_webui/utils/data_analysis/event_logger.py

async def log_event(*,
    event_type: str,
    user_id: str,
    chat_id: str | None = None,
    message_id: str | None = None,
    payload: dict,
    schema_version: int = 1,
    dataset_id: str | None = None,
    chart_type: str | None = None,
    tool_name: str | None = None,
    duration_ms: int | None = None,
    success: bool = True,
    error_code: str | None = None,
) -> None: ...
```

- Non-blocking。`asyncio.create_task(log_event(...))` 從 tool function fire-and-forget
- Queue 滿（10k）→ `log.warning` + drop newest

```ts
// src/lib/apis/data-analysis/events.ts

export async function logEvent(payload: {
    event_type: string;
    chat_id?: string;
    message_id?: string;
    payload: Record<string, any>;
    duration_ms?: number;
    dataset_id?: string;
    chart_type?: string;
}): Promise<void>;  // fire-and-forget, never await
```

對應 backend endpoint：`POST /api/v1/data-analysis/events` (whitelist event_type)

---

## Worker Lifecycle

```python
# main.py
@app.on_event('startup')
async def _startup():
    start_event_worker()

@app.on_event('shutdown')
async def _shutdown():
    await stop_event_worker()
```

Batch insert：每 5s 或滿 100 events 觸發。

---

## Soft Delete

```python
# Hook native delete_chat_by_id
await DataAnalysisEvents.mark_deleted(chat_id=chat_id)
```

```sql
UPDATE data_analysis_events
SET is_deleted = TRUE, deleted_at = $1
WHERE chat_id = $2;
```

預設查詢過濾 `WHERE is_deleted = FALSE`。

---

## Implementation Steps (~3.25d)

| # | Step | Days |
|---|---|---|
| 1 | Migration | 0.25 |
| 2 | Model + bulk_insert | 0.25 |
| 3 | Async worker + queue | 0.5 |
| 4 | Tool function emit integration (×5 methods) | 0.5 |
| 5 | Frontend events endpoint + client (×5 emit points) | 0.5 |
| 6 | Thinking detection in chat forwarder | 0.5 |
| 7 | Soft delete hook | 0.25 |
| 8 | Tests + acceptance | 0.5 |

---

## Anti-patterns

- 同步 `await log_event` 在 chat path → `asyncio.create_task`
- Tool failed 不 emit failed event → except block 也要 emit
- Thinking 全文存 chat metadata → 只 ledger 存
- Frontend 直接寫 DB → 走 `/data-analysis/events`
- Random event_type → enum const
- Hard delete → soft delete only
- Schema 變動不 bump version → must bump
- 假設 queue 永有空間 → log + metric on QueueFull
- 每個 emit 重複寫 `workspace='data-analysis'` → helper 預設

---

## Acceptance

- [ ] Migration 過，6 個 index 在
- [ ] `bulk_insert` / `mark_deleted` unit tests
- [ ] Background worker 正常 batch + shutdown drain
- [ ] 12 個 P0 events 全部覆蓋 emit 點
- [ ] Frontend events endpoint whitelist 拒未知 event_type
- [ ] Thinking 偵測 vertical-only，不污染 generic chat
- [ ] Soft delete：刪 chat 後 events `is_deleted=TRUE`
- [ ] E2E 測：完整 workflow 看 trace 順序正確
- [ ] Queue full 測：11k events 前 1k 丟失但 log warning
- [ ] 12 個 events 各至少 1 fixture，能跑 query examples

---

## 跨檔關聯

- Tool emit 整合：[`tools-schema.brief.md`](./tools-schema.brief.md)
- Frontend emit 點：[`frontend-spec.brief.md`](./frontend-spec.brief.md) §1.8 step-by-step
- 為什麼用 ledger 而非 chat.metadata：teaching `event-ledger.md` §1
- DB 與 adapter 解耦：[`database-adapter.brief.md`](./database-adapter.brief.md)（不互相依賴）
