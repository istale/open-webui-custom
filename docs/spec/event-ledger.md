# Event Ledger Spec — Vertical Workspace 行為觀測層

> ⚡ **Quick reference**: [`event-ledger.brief.md`](./event-ledger.brief.md) — 純 schema + event 清單。**修改本檔時必須同步更新 brief 版**。
>
> **目的**：把 vertical workspace 內所有「使用者—系統」互動事件記錄下來，作為未來行為分析、ML 訓練資料、產品迭代依據的 single source of truth。
>
> **依賴**：[`tools-schema.md`](./tools-schema.md)（tool calling 機制）、[`data-analysis-vertical-spec.md`](./data-analysis-vertical-spec.md)（domain 流程）、[`frontend-spec.md`](./frontend-spec.md)（frontend emit 點）

---

## 1. 為什麼要做這個

### 1.1 Two-tier Persistence（兩層儲存）

Open WebUI 原生的 chat table（`chat.chat` jsonb 欄位）存的是 **live state** — 為 UI render 與 reload 還原而設計：

```
chat.chat = {
    history: { messages: { [id]: { role, content, toolCalls, ... } } },
    metadata: { workspace_type, data_analysis: { selected_dataset_id, ... } }
}
```

這份資料對 UI 來說剛好（reactive、容易 round-trip），但對**分析查詢**來說是惡夢：

- 跨 user / 跨 chat 統計 → 全表掃 + JSONB parse + application 層 regex 抽取
- 沒有 timestamp index 可以做時間序列分析
- Schema 升級 = 改 JSON blob 內結構（容易破壞舊 chat）
- 想分析「使用者刪掉的 chat 也要算進去」→ 已 hard delete 沒了

所以加**第二層 ledger**：append-only、有 column index、結構穩定可 evolve、與 UI 解耦。

```
            ┌─────────────────────────┐
            │ Tool execution          │
            │ (query / render / ...) │
            └────────────┬────────────┘
                         │
            ┌────────────┴────────────┐
            ↓                         ↓
   ┌────────────────┐        ┌────────────────────┐
   │ Live state     │        │ Analytics ledger   │
   │ chat.chat.     │        │ data_analysis_     │
   │   metadata     │        │   events table     │
   └───────┬────────┘        └────────┬───────────┘
           │                          │
           ↓                          ↓
   UI render / reload          Batch analytics / ML
   (immediate, sync)           (async, eventual)
```

### 1.2 用 `chat.metadata` 也行嗎？不行，這 5 點

1. **Query pattern 不同**：分析要 `WHERE event_type = X AND ts > Y` 這種 OLAP query，chat 表是 single-row OLTP
2. **是否被刪不能影響歷史分析**：使用者刪 chat 後，原本 `chat.metadata` 跟著消失；ledger 用 soft delete 保住
3. **Schema 演進**：ledger 加欄位是純 SQL migration；改 JSON blob 內結構要寫 application 層 backfill
4. **Background async write**：ledger 寫入失敗不影響 chat completion；混在 chat metadata 寫入失敗 → user 看到錯
5. **Cross-chat 事件**：例如「dataset.selected」可能發生在歡迎頁（沒 chat id），無法塞 chat metadata

### 1.3 設計目標（按優先序）

| 目標 | 怎麼達成 |
|---|---|
| 1. 不影響 chat 性能 | Async write + 背景 worker batch insert |
| 2. 失敗不丟事件 | In-memory queue + bounded retry，極端情況 log 警告允許小量丟失 |
| 3. 容易查詢 | column 化 + 6 個 index + jsonb payload |
| 4. Schema 可演進 | Per-event `schema_version` |
| 5. 完整保留歷史 | Soft delete via `is_deleted`，不真刪 |
| 6. 內部使用 | 不做 anonymize / GDPR 流程，存全文 |
| 7. ML 訓練可用 | `prompt → thinking → tool_calls → outcome` 可串成完整 trace |

---

## 2. Table Schema

### 2.1 DDL

```sql
CREATE TABLE data_analysis_events (
    -- 識別與時序
    id            TEXT PRIMARY KEY,            -- uuid4
    ts            BIGINT NOT NULL,             -- event timestamp (ms since epoch)

    -- WHO
    user_id       TEXT NOT NULL,
    user_org_id   TEXT,                        -- 預留 multi-tenant

    -- WHERE (chat / message context)
    chat_id       TEXT,                        -- nullable for workspace-level events
    message_id    TEXT,                        -- nullable for non-message events
    workspace     TEXT NOT NULL DEFAULT 'data-analysis',

    -- WHAT
    event_type    TEXT NOT NULL,               -- e.g. 'tool.query_dataset.succeeded'
    schema_version INT NOT NULL DEFAULT 1,

    -- 結構化內容
    payload       JSONB NOT NULL,              -- event-specific structured data

    -- Denormalized 常用欄位（給 index / 快速 filter）
    dataset_id    TEXT,
    chart_type    TEXT,
    tool_name     TEXT,
    duration_ms   INT,
    success       BOOLEAN NOT NULL DEFAULT TRUE,
    error_code    TEXT,                        -- nullable

    -- Soft delete
    is_deleted    BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at    BIGINT
);

CREATE INDEX idx_events_user_ts        ON data_analysis_events (user_id, ts);
CREATE INDEX idx_events_chat_ts        ON data_analysis_events (chat_id, ts) WHERE is_deleted = FALSE;
CREATE INDEX idx_events_event_type_ts  ON data_analysis_events (event_type, ts);
CREATE INDEX idx_events_dataset_ts     ON data_analysis_events (dataset_id, ts) WHERE dataset_id IS NOT NULL;
CREATE INDEX idx_events_chart_type_ts  ON data_analysis_events (chart_type, ts) WHERE chart_type IS NOT NULL;
CREATE INDEX idx_events_success_ts     ON data_analysis_events (success, ts);
```

### 2.2 欄位職責

| 欄位 | 用途 | 為什麼這樣設計 |
|---|---|---|
| `id` | uuid4 主鍵 | Idempotent — retry 不重複；不洩漏寫入順序 |
| `ts` | 毫秒時間戳 | 整數比 datetime 快、跨時區 compatible、適合分析 |
| `user_id` | 觸發者 | 必填，所有事件都有歸屬 |
| `user_org_id` | 組織 ID | 預留，目前 NULL；未來 multi-tenant 不用 migration |
| `chat_id`, `message_id` | 上下文 | 可空 — 例如 `workspace.opened` 沒 chat |
| `workspace` | 命名空間 | 預設 `'data-analysis'`，未來其他 vertical 共用此表 |
| `event_type` | 事件類型 | 字串列舉，按 `<area>.<action>.<outcome>` 命名 |
| `schema_version` | payload 版本 | 預設 1；payload 結構升級時 +1，舊 reader 走兼容路徑 |
| `payload` | event 詳細內容 | JSONB，每種 event_type 自有 schema |
| Denormalized 欄位 | 高頻查詢加速 | 在 payload 內也存一份（雙寫），但 column 提供 index |
| `is_deleted` | soft delete | 預設 false；user 刪 chat 時對應 events flip true |
| `deleted_at` | 刪除時點 | 分析「使用者刪除頻率」時用 |

### 2.3 Index 策略

6 個 index 覆蓋常見 query：

| Index | 對應 query 樣板 |
|---|---|
| `(user_id, ts)` | 「user X 過去 N 天行為」 |
| `(chat_id, ts) WHERE is_deleted=false` | 「某個 chat 完整 trace」 |
| `(event_type, ts)` | 「過去 N 天所有 X 事件」 |
| `(dataset_id, ts)` | 「dataset Y 的使用熱度」 |
| `(chart_type, ts)` | 「control chart 平均 render 時間」 |
| `(success, ts)` | 「失敗事件率」 |

Partial index（`WHERE`）：縮小 index 大小，提升查詢速度。

### 2.4 Migration

新建 `backend/open_webui/migrations/versions/<next>_add_data_analysis_events.py`：

```python
"""add data_analysis_events table"""
import peewee as pw
from peewee_migrate import Migrator

def migrate(migrator: Migrator, database, *, fake=False):
    @migrator.create_model
    class DataAnalysisEvent(pw.Model):
        id = pw.TextField(primary_key=True)
        ts = pw.BigIntegerField(index=False)
        user_id = pw.TextField()
        user_org_id = pw.TextField(null=True)
        chat_id = pw.TextField(null=True)
        message_id = pw.TextField(null=True)
        workspace = pw.TextField(default='data-analysis')
        event_type = pw.TextField()
        schema_version = pw.IntegerField(default=1)
        payload = pw.TextField()  # JSONField in real impl
        dataset_id = pw.TextField(null=True)
        chart_type = pw.TextField(null=True)
        tool_name = pw.TextField(null=True)
        duration_ms = pw.IntegerField(null=True)
        success = pw.BooleanField(default=True)
        error_code = pw.TextField(null=True)
        is_deleted = pw.BooleanField(default=False)
        deleted_at = pw.BigIntegerField(null=True)

        class Meta:
            table_name = 'data_analysis_events'

    migrator.add_index('data_analysis_events', 'user_id', 'ts')
    migrator.add_index('data_analysis_events', 'chat_id', 'ts')
    migrator.add_index('data_analysis_events', 'event_type', 'ts')
    migrator.add_index('data_analysis_events', 'dataset_id', 'ts')
    migrator.add_index('data_analysis_events', 'chart_type', 'ts')
    migrator.add_index('data_analysis_events', 'success', 'ts')

def rollback(migrator: Migrator, database, *, fake=False):
    migrator.remove_model('data_analysis_events')
```

---

## 3. Event Catalog

### 3.1 命名慣例

`<area>.<action>[.<outcome>]`

- `area`：哪個 domain（`workspace` / `dataset` / `prompt` / `model` / `tool.<name>` / `chart` / `message` / `stream` / `followup`）
- `action`：動詞（`opened` / `selected` / `submitted` / `started` / `completed` / `succeeded` / `failed` / ...）
- `outcome`（可選）：`succeeded` / `failed` 等結果分支

範例：`tool.render_chart.succeeded`、`stream.timeout`、`workspace.opened`。

### 3.2 P0 Events（MVP 必做，11 種）

| event_type | 觸發點 | payload 必填欄位 | 為什麼存 |
|---|---|---|---|
| `workspace.opened` | 進入 `/workspace/data-analysis` 路由 | `entry_path` (sidebar / direct / sidebar-history) | 進入頻率 / 主要入口統計 |
| `dataset.selected` | DatasetPanel select-dataset event | `dataset_id`, `prev_dataset_id`, `from` (chip / row / search) | 哪些 dataset 最熱、切換頻率 |
| `prompt.submitted` | User 按 Enter 送訊息 | `prompt_text`, `prompt_length`, `model`, `is_first_in_chat` | 使用者怎麼問；ML 訓練 prompt sample |
| `model.thinking_completed` | 偵測到 `</think>` boundary | `thinking_text`, `n_chars`, `duration_ms` | 模型推理鏈；ML 蒸餾用；理解模型決策 |
| `tool.query_dataset.succeeded` | query_dataset return 成功 | `sql`, `query_id`, `row_count`, `truncated`, `duration_ms` | Query 模式 + 性能 |
| `tool.query_dataset.failed` | query_dataset 例外 | `sql`, `error_code`, `error_message`, `duration_ms` | 失敗模式（query 寫錯 / timeout / 權限）|
| `tool.render_chart.succeeded` | render_chart return 成功 | `chart_type`, `query_id`, `chart_id`, `image_size_bytes`, `duration_ms`, `statistics` | Chart 性能 + 結果指標 |
| `tool.render_chart.failed` | render_chart 例外 | `chart_type`, `error_code`, `error_message`, `duration_ms` | matplotlib render 失敗模式 |
| `chart.rendered` | 前端收到 chart attachment 完成渲染 | `chart_id`, `chart_type`, `displayed_in` (chat-placeholder / canvas-card) | User 視角看到結果（vs server 視角的 tool.succeeded）|
| `message.assistant_completed` | Native chat message done=true | `message_id`, `total_duration_ms`, `tool_call_count`, `n_chars`, `had_thinking` | 整體 conversation turn 統計 |
| `stream.timeout` | streamDataAnalysis idle / overall timeout（沿用 Phase 2.5 P0 機制）| `chat_id`, `elapsed_ms`, `last_event_type` | streaming 卡死率 |
| `stream.aborted` | User 主動 abort 或 connection drop | `chat_id`, `reason` (user-cancel / network / server-error) | User 中斷模式 |
| `followup.clicked` | User 點 follow-up 建議 | `followup_text`, `source_message_id`, `followup_index` | 哪些 follow-up 引導有效；改善 prompt strategy |

合計 **12 個 P0**（含 `followup.clicked`）。

### 3.3 Backlog Events（非 MVP 範圍）

加入規格但不在 Day 1–7 範圍：

| event_type | 觸發點 | 為什麼 backlog |
|---|---|---|
| `chart.viewed` | Canvas card 進入 viewport（IntersectionObserver） | 需 frontend 整合，可後加 |
| `chart.locate_clicked` | User 點 `<ChatPlaceholder>` 的「定位」按鈕 | 需 frontend 整合，可後加 |
| `message.thumbs_up` / `message.thumbs_down` | User 反饋 | 需 native UI 整合或加 vertical button |
| `chart.image_load_error` | `<img on:error>` | 視覺異常追蹤，PreFlight 不必 |
| `dataset.access_denied` | RBAC 拒絕（adapter raise PermissionDeniedError）| 監控用，等 RBAC 規模化才需要 |

### 3.4 Schema versioning

每種 `event_type` 的 `payload` 結構視為獨立 schema：

- 新增欄位 → 不變 `schema_version`（backward-compat）
- 改欄位 type 或刪欄位 → bump `schema_version` + reader 處理多版本

```python
def parse_query_dataset_event(event):
    if event['schema_version'] == 1:
        return event['payload']
    elif event['schema_version'] == 2:
        # v2 split 'sql' into 'sql_template' + 'sql_params'
        return migrate_v1_to_v2(event['payload'])
```

---

## 4. Emit Mechanism — 寫入策略

### 4.1 同步 vs 異步

**所有 ledger 寫入一律異步**：

| 場景 | 同步寫 | 異步寫 |
|---|---|---|
| chat.chat.metadata | ✅（UI 需要立即 reactive） | ❌ |
| data_analysis_events | ❌ | ✅（分析容忍秒級延遲） |

### 4.2 In-memory queue + Background Worker

```python
# backend/open_webui/utils/data_analysis/event_logger.py

import asyncio
import time
import logging
from uuid import uuid4
from typing import Any

log = logging.getLogger(__name__)

_event_queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)
_worker_task: asyncio.Task | None = None


async def log_event(
    *,
    event_type: str,
    user_id: str,
    chat_id: str | None = None,
    message_id: str | None = None,
    payload: dict[str, Any],
    schema_version: int = 1,
    # Denormalized columns (optional, extracted from payload by convention)
    dataset_id: str | None = None,
    chart_type: str | None = None,
    tool_name: str | None = None,
    duration_ms: int | None = None,
    success: bool = True,
    error_code: str | None = None,
) -> None:
    """Non-blocking. Caller never awaits DB I/O.

    If queue full, oldest event is dropped (logged warning). Acceptable
    trade-off for never blocking chat completion.
    """
    event = {
        'id': uuid4().hex,
        'ts': int(time.time() * 1000),
        'user_id': user_id,
        'chat_id': chat_id,
        'message_id': message_id,
        'workspace': 'data-analysis',
        'event_type': event_type,
        'schema_version': schema_version,
        'payload': payload,
        'dataset_id': dataset_id,
        'chart_type': chart_type,
        'tool_name': tool_name,
        'duration_ms': duration_ms,
        'success': success,
        'error_code': error_code,
        'is_deleted': False,
    }
    try:
        _event_queue.put_nowait(event)
    except asyncio.QueueFull:
        log.warning('event queue full; dropped event_type=%s', event_type)


async def _flush_worker():
    """Drains queue, batches inserts every 5s or 100 events."""
    while True:
        batch = []
        try:
            # Wait for first event (or timeout to flush partial batch)
            event = await asyncio.wait_for(_event_queue.get(), timeout=5.0)
            batch.append(event)
            # Greedy drain up to 100 more
            while len(batch) < 100:
                try:
                    batch.append(_event_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            await DataAnalysisEvents.bulk_insert(batch)
        except asyncio.TimeoutError:
            continue  # no events in 5s, loop
        except Exception as e:
            log.error('event flush failed: %s; events lost: %d', e, len(batch))


def start_event_worker():
    """Called from main.py @app.on_event('startup')."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_flush_worker())


async def stop_event_worker():
    """Called from main.py @app.on_event('shutdown')."""
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        # Final drain attempt
        remaining = []
        while not _event_queue.empty():
            try:
                remaining.append(_event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if remaining:
            try:
                await DataAnalysisEvents.bulk_insert(remaining)
            except Exception as e:
                log.error('final flush failed: %s; events lost: %d', e, len(remaining))
```

### 4.3 失敗策略

| 失敗情境 | 行為 | 事件下場 |
|---|---|---|
| Queue 滿（10k 上限） | `log.warning`，新 event 丟棄 | 丟最新進來的 |
| DB insert 失敗（暫時） | 整 batch 一起丟 | 接受丟失（不重試，避免 cascade）|
| DB 永久失敗（長時間 down） | log error 連續報警 | 累積到 queue 滿後丟失 |
| Server crash | queue 內未 flush events | 丟失（最多 5s + 100 events） |

**接受少量丟失**是設計選擇 — 行為分析容忍 < 1% 遺失。若未來需要 100% 保證，加 WAL（先寫本地 file，crash recover 時 replay）— +0.5d 工時。

### 4.4 Idempotency

- 主鍵是 `id = uuid4().hex` — 每次 emit 都產新 id
- Tool retry → 兩個事件（這是對的，「retry 也是分析素材」）
- 網路斷線重發 → 不會重複（uuid 隨機，新 id）

---

## 5. 在程式碼哪裡 emit（具體位置）

### 5.1 Tool functions（在 `backend/open_webui/tools/data_analysis/tool_module.py`）

每個 method 起頭記錄 `started`、return 前記錄 `succeeded`、except block 記錄 `failed`：

```python
class Tools:
    def query_dataset(self, dataset_id, query, max_rows=100, *, __user__=None) -> dict:
        """..."""
        t0 = time.perf_counter()
        try:
            result = self.repo.execute_query(...)
            query_id = self.query_cache.put(...)
            duration_ms = int((time.perf_counter() - t0) * 1000)

            asyncio.create_task(log_event(  # fire-and-forget
                event_type='tool.query_dataset.succeeded',
                user_id=__user__['id'],
                chat_id=__user__.get('current_chat_id'),  # 從 metadata 注入
                message_id=__user__.get('current_message_id'),
                tool_name='query_dataset',
                dataset_id=dataset_id,
                duration_ms=duration_ms,
                success=True,
                payload={
                    'sql': query,
                    'query_id': query_id,
                    'row_count': result.row_count,
                    'truncated': result.truncated,
                },
            ))
            return {'query_id': query_id, ...}
        except QueryTimeoutError as e:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            asyncio.create_task(log_event(
                event_type='tool.query_dataset.failed',
                user_id=__user__['id'],
                tool_name='query_dataset',
                dataset_id=dataset_id,
                duration_ms=duration_ms,
                success=False,
                error_code='QUERY_TIMEOUT',
                payload={'sql': query, 'error_message': str(e)},
            ))
            raise
        # ... 其他 except 分支同上
```

### 5.2 Chat completion middleware（thinking events）

依 Day 1 inventory 結果，三種注入方式：

**A. 在 streaming SSE forwarder 內偵測 `<think>` boundaries**：
```python
# 偽碼
async def forward_chat_stream(upstream, chat_id, user_id, message_id):
    in_thinking = False
    thinking_buffer = []
    thinking_started_at = None

    async for chunk in upstream:
        text = extract_delta_content(chunk)
        if '<think>' in text and not in_thinking:
            in_thinking = True
            thinking_started_at = time.time()
            # 不 emit started，避免雜訊
        if in_thinking:
            thinking_buffer.append(text)
            if '</think>' in text:
                in_thinking = False
                full = ''.join(thinking_buffer)
                # 抽取 <think>...</think> 內容
                thinking_text = extract_think_content(full)
                duration_ms = int((time.time() - thinking_started_at) * 1000)
                asyncio.create_task(log_event(
                    event_type='model.thinking_completed',
                    user_id=user_id,
                    chat_id=chat_id,
                    message_id=message_id,
                    duration_ms=duration_ms,
                    payload={
                        'thinking_text': thinking_text,
                        'n_chars': len(thinking_text),
                    },
                ))
                thinking_buffer = []
        yield chunk  # 原樣轉發給 frontend
```

**B. Vertical-only wrapper**：只在 `metadata.workspace_type === 'data-analysis'` 走這個 forwarder。Day 1 inventory 確認 hook 點。

**C. 全 chat 都 emit**：適用於想分析 generic chat 的 thinking 也算數的情境（範圍超出 vertical，PM 決定）。

**目前默認 B**（vertical-only），降低污染。

### 5.3 Frontend events（`followup.clicked`、`prompt.submitted`、`workspace.opened`、`chart.rendered`）

前端透過 vertical 的 events API 上傳：

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
}) {
    // Fire-and-forget; don't await
    fetch(`${WEBUI_API_BASE_URL}/data-analysis/events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json',
                   Authorization: `Bearer ${localStorage.token}` },
        body: JSON.stringify(payload),
    }).catch((err) => console.warn('[event-logger] failed', err));
}
```

對應 backend endpoint：

```python
# backend/open_webui/routers/data_analysis.py

@router.post('/events')
async def log_frontend_event(
    request: Request,
    payload: FrontendEventPayload,
    user=Depends(get_verified_user),
):
    # Whitelist allowed event_types from frontend
    if payload.event_type not in FRONTEND_ALLOWED_EVENT_TYPES:
        raise HTTPException(400, 'event_type not allowed from frontend')
    await log_event(
        event_type=payload.event_type,
        user_id=user.id,
        chat_id=payload.chat_id,
        message_id=payload.message_id,
        payload=payload.payload,
        ...
    )
    return {'ok': True}

FRONTEND_ALLOWED_EVENT_TYPES = {
    'workspace.opened',
    'prompt.submitted',
    'followup.clicked',
    'chart.rendered',
    'stream.aborted',  # client-side abort
    # backlog: chart.viewed, chart.locate_clicked, thumbs_up/down
}
```

### 5.4 Stream lifecycle events

`streamDataAnalysis.ts` 已有 timeout / abort 邏輯（Phase 2.5 P0），擴展讓它在事件發生時 call `logEvent(...)`：

```ts
// streamDataAnalysis.ts
} catch (err) {
    if (err.name === 'DataAnalysisStreamTimeoutError') {
        logEvent({
            event_type: 'stream.timeout',
            chat_id, message_id,
            duration_ms: elapsed,
            payload: { last_event_type: lastEventType },
        });
    }
    // ...
}
```

---

## 6. Soft Delete

### 6.1 機制

User 刪 chat 時，相關 events 標 `is_deleted = TRUE`、`deleted_at = now_ms()`，**不真刪**：

```python
# backend/open_webui/models/chats.py — hook into delete_chat_by_id

async def delete_chat_by_id(chat_id: str, user_id: str):
    # ... existing native logic ...
    await Chats.delete(chat_id)

    # Vertical hook
    await DataAnalysisEvents.mark_deleted(chat_id=chat_id)
```

`DataAnalysisEvents.mark_deleted`：

```sql
UPDATE data_analysis_events
SET is_deleted = TRUE, deleted_at = $1
WHERE chat_id = $2;
```

### 6.2 查詢預設行為

分析師預設過濾掉 deleted（若 query 不關心歷史）：

```sql
SELECT ... FROM data_analysis_events
WHERE is_deleted = FALSE
  AND ts > now_ms() - 7*86400*1000;
```

但「**有多少 user 刪了 chat**」分析就不過濾：

```sql
SELECT user_id, COUNT(*) FROM data_analysis_events
WHERE event_type = 'workspace.opened' AND is_deleted = TRUE
GROUP BY user_id;
```

### 6.3 不做的事

- ❌ Anonymize（內部使用，無 GDPR 壓力）
- ❌ 自動 retention prune（先存著，未來真的太大再說）
- ❌ Hard delete fallback（簡化邏輯）

---

## 7. Query Examples（給未來分析師看）

### 7.1 過去 7 天最常用的 dataset

```sql
SELECT dataset_id, COUNT(*) AS uses
FROM data_analysis_events
WHERE event_type = 'dataset.selected'
  AND ts > extract(epoch from now() - interval '7 days') * 1000
  AND is_deleted = FALSE
GROUP BY dataset_id
ORDER BY uses DESC
LIMIT 10;
```

### 7.2 各 chart_type 平均 render 時間

```sql
SELECT chart_type, AVG(duration_ms) AS avg_ms, COUNT(*) AS n
FROM data_analysis_events
WHERE event_type = 'tool.render_chart.succeeded'
  AND ts > extract(epoch from now() - interval '30 days') * 1000
GROUP BY chart_type
ORDER BY avg_ms DESC;
```

### 7.3 Tool 失敗率

```sql
SELECT
    tool_name,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) AS ok,
    SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) AS failed,
    100.0 * SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) / COUNT(*) AS failure_pct
FROM data_analysis_events
WHERE tool_name IS NOT NULL
  AND ts > extract(epoch from now() - interval '7 days') * 1000
GROUP BY tool_name;
```

### 7.4 ML 訓練資料 export（per chat conversation trace）

```sql
SELECT chat_id, ts, event_type, payload
FROM data_analysis_events
WHERE chat_id IS NOT NULL
  AND event_type IN (
    'prompt.submitted',
    'model.thinking_completed',
    'tool.query_dataset.succeeded',
    'tool.render_chart.succeeded',
    'message.assistant_completed'
  )
  AND is_deleted = FALSE
ORDER BY chat_id, ts;
```

→ 取出後 group by `chat_id`，每 chat 變成一條 trace，作為 LLM fine-tune 樣本。

### 7.5 Follow-up 點擊轉換率

```sql
SELECT
    fp.payload->>'followup_text' AS suggestion,
    COUNT(*) AS shown,
    SUM(CASE WHEN clicked.id IS NOT NULL THEN 1 ELSE 0 END) AS clicked,
    100.0 * SUM(CASE WHEN clicked.id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*) AS ctr
FROM (
    SELECT id, payload, ts, message_id
    FROM data_analysis_events
    WHERE event_type = 'message.assistant_completed'
      AND payload ? 'followups'  -- 假設 payload 有 followups 列表
) AS fp
LEFT JOIN data_analysis_events clicked
    ON clicked.event_type = 'followup.clicked'
   AND clicked.payload->>'source_message_id' = fp.message_id
GROUP BY suggestion
ORDER BY ctr DESC;
```

---

## 8. Implementation Steps（按順序執行）

每步可獨立 demo + 1–2 個 commit。

### Step 1 — DB Migration（0.25d）
1. 新建 migration file `<next>_add_data_analysis_events.py`
2. 跑 migration 驗證表 + index 建立
3. **Demo**：`SELECT * FROM data_analysis_events`（empty）

### Step 2 — Model + bulk_insert（0.25d）
1. `backend/open_webui/models/data_analysis_events.py`
2. `DataAnalysisEvents.bulk_insert(events: list[dict])`
3. `DataAnalysisEvents.mark_deleted(chat_id: str)`
4. Unit test：insert 100 events → query back

### Step 3 — Async worker（0.5d）
1. `backend/open_webui/utils/data_analysis/event_logger.py`（per §4.2）
2. `start_event_worker` / `stop_event_worker` 串到 `main.py` lifespan
3. Stress test：emit 1000 events 看 batch 寫入

### Step 4 — Tool function 整合（0.5d）
1. 修改 `tool_module.py` 5 個 method 各加 `succeeded` / `failed` emit
2. Unit test：mock log_event，驗證 emit args

### Step 5 — Frontend events endpoint + client（0.5d）
1. `POST /api/v1/data-analysis/events`（per §5.3）
2. `src/lib/apis/data-analysis/events.ts` client
3. Frontend 5 處 call point：
   - `+layout.svelte` mount → `workspace.opened`
   - prompt 送出 → `prompt.submitted`
   - follow-up click → `followup.clicked`
   - canvas card mount → `chart.rendered`
   - streamDataAnalysis abort → `stream.aborted`

### Step 6 — Thinking detection（0.5d）
1. 依 inventory Day 1 結果選 Plan B（vertical-only wrapper）
2. 在 chat completion forwarder 內加 `<think>` boundary 偵測
3. Emit `model.thinking_completed`
4. **Demo**：送一句 → DB 看到 thinking event 含 thinking_text

### Step 7 — Soft delete hook（0.25d）
1. Hook into native `delete_chat_by_id` flow
2. Verify update on delete
3. **Demo**：刪 chat → 對應 events `is_deleted = true`

### Step 8 — Tests + Acceptance（0.5d）
1. End-to-end：跑一個分析 workflow，驗 DB 內事件數量、order、payload 正確
2. Stress test：100 chats 同時跑，驗 worker 不丟事件（< 1% loss）
3. Failure test：拔網路 / kill DB → restore → 行為正常

**總工時：~3.25 days**

---

## 9. Deployment / Graceful Shutdown

### 9.1 為什麼這節重要

`_event_queue` 容量 10k，背景 worker 每 5s / 100 events 才 flush 一次。Worst case 在 worker flush 之間，記憶體內最多累積 100 events 沒落地。**正常 shutdown 流程**會給 worker 機會 drain，但若 process 被 SIGKILL 強制中止 → 這批 events 全丟。

### 9.2 ASGI server 層的 grace period 設定

#### Uvicorn 直接運行
```bash
uvicorn open_webui.main:app \
    --host 0.0.0.0 --port 8080 \
    --timeout-graceful-shutdown 15
```
（Uvicorn 1.0 之後預設 30s，但部署環境經常被外層 override 成 5s）

#### Gunicorn + Uvicorn worker
```bash
gunicorn open_webui.main:app \
    -k uvicorn.workers.UvicornWorker \
    --graceful-timeout 15 \
    --timeout 120
```

#### Kubernetes Pod
```yaml
spec:
  terminationGracePeriodSeconds: 20  # 給 worker 15s drain + 5s buffer
  containers:
    - name: open-webui
      lifecycle:
        preStop:
          exec:
            # 收到 SIGTERM 前先送 in-flight requests 回到 client，
            # 給 event worker 全速 drain queue
            command: ["/bin/sh", "-c", "sleep 5"]
```

### 9.3 Drain budget 計算

最差狀況：queue 滿（10k events），DB bulk_insert 100 events 約 50ms：
- 100 batches × 50ms = **5 秒**完整 drain

設定 grace period **15 秒**（5s drain + 10s buffer for in-flight HTTP requests）就足夠。

### 9.4 Drain 失敗的最後一道防線（可選 P1）

若 graceful shutdown 仍可能發生（例如 OOM kill 不給 grace），可加 file fallback：

```python
async def stop_event_worker():
    """Final drain — write any remaining queue to local file as JSONL."""
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()

    remaining = []
    while not _event_queue.empty():
        try:
            remaining.append(_event_queue.get_nowait())
        except asyncio.QueueEmpty:
            break

    if not remaining:
        return

    # 1st attempt: DB
    try:
        await DataAnalysisEvents.bulk_insert(remaining)
        return
    except Exception as e:
        log.warning('final DB flush failed: %s; falling back to file', e)

    # 2nd attempt: local JSONL file (recovery script picks up next startup)
    fallback_path = Path('data/cache/data-analysis/events-pending.jsonl')
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    with fallback_path.open('a') as f:
        for event in remaining:
            f.write(json.dumps(event) + '\n')

    log.info('drained %d events to %s', len(remaining), fallback_path)
```

`start_event_worker` 開頭 replay file（若存在）：
```python
def start_event_worker():
    fallback_path = Path('data/cache/data-analysis/events-pending.jsonl')
    if fallback_path.exists():
        log.info('replaying pending events from %s', fallback_path)
        with fallback_path.open() as f:
            for line in f:
                event = json.loads(line)
                _event_queue.put_nowait(event)
        fallback_path.unlink()
    # ... start the worker task ...
```

**P1 不 P0**：只在你們發現 OOM kill 真的常發生時才需要。MVP 接受 5s 內 worst-case 100 events 丟失。

### 9.5 監控 metric

加一個 health endpoint 暴露 worker 狀態，方便 ops：

```python
@router.get('/healthz/event-worker')
async def event_worker_health():
    return {
        'queue_size': _event_queue.qsize(),
        'queue_capacity': _event_queue.maxsize,
        'worker_alive': _worker_task is not None and not _worker_task.done(),
        'queue_full_warning': _event_queue.qsize() > 0.8 * _event_queue.maxsize,
    }
```

Prometheus / Grafana 抓這個 endpoint，告警「queue > 80% 持續 1 分鐘」 = backlog 在累積，DB 可能掛了。

---

## 10. Anti-patterns

| 反 pattern | 為什麼錯 | 正解 |
|---|---|---|
| 同步 `await log_event(...)` 在 chat completion 路徑 | 阻塞 UI streaming | `asyncio.create_task(log_event(...))` |
| Tool function 失敗時不 emit failed event | 失敗模式無資料 | `try/except` 兩邊都 emit |
| 把 thinking 全文也存進 chat metadata | chat row 膨脹 | 只 ledger 存全文，chat 走原生 `<think>` content |
| 在 frontend 直接寫 DB | 前端無權限、繞過 RBAC | 走 backend endpoint `/data-analysis/events` |
| Emit event 時用 random 字串當 event_type | 無 schema，分析時混亂 | 嚴格 enum，定義在 const file |
| 沒有 `is_deleted` 直接 hard delete | 失去歷史分析能力 | soft delete 永遠保留 |
| Schema 改動不 bump `schema_version` | 舊 reader 讀新 event 會崩 | 任何 payload 結構變動 → bump |
| 假設 queue 永遠有空間 | 高峰會丟事件不知道 | `QueueFull` log warning + metric |
| 寫死 `workspace = 'data-analysis'` 在每個 emit 點 | 未來其他 vertical 共用 | `log_event` helper 預設好，不重複 |

---

## 11. Acceptance / DOD

- [ ] DB migration 跑過，新表 + 6 個 index 都在
- [ ] `DataAnalysisEvents.bulk_insert` + `.mark_deleted` 有 unit test
- [ ] Background worker 啟動後正常 batch 寫入，shutdown 時 final drain 嘗試
- [ ] Tool function 5 個 method 全部 emit `succeeded` / `failed`，覆蓋 12 個 P0 events
- [ ] Frontend events endpoint 有 whitelist，rejected unknown event_type
- [ ] Thinking 偵測在 vertical-only path 內運作，generic chat 不受影響
- [ ] Soft delete：刪 chat 後對應 events `is_deleted = TRUE`
- [ ] End-to-end 測試：跑一個 workflow，DB 內看到完整 event trace（順序正確）
- [ ] Queue full 測試：emit 11k events，前 1k 丟失但 log warning，剩下正常寫
- [ ] 12 個 P0 event_type 各至少一筆 fixture，能用 §7 的 query examples 跑通
