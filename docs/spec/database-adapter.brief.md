# Database Adapter — Brief / Contract Version

> **Quick reference of `database-adapter.md`. 修改本檔時必須同步更新 teaching 版。**
>
> **架構**：Hexagonal / Port-and-Adapter — vertical 程式只認抽象 Port，HTTP / InMemory adapter 都實作同一介面。

---

## Architecture

```
Vertical tools / routes
        ↓ uses
DatasetRepository Protocol (Port)
        ↓ implemented by
{HttpAdapter, InMemoryAdapter, RecordReplayAdapter}
        ↓ talks to
External standalone data system
```

切換 adapter = 改 config，**vertical 程式 0 改動**。

---

## Port (`backend/open_webui/utils/data_analysis/repository.py`)

### DTOs (frozen dataclass)

```python
@dataclass(frozen=True)
class DatasetMeta:
    id: str
    name: str
    description: str
    row_count: int
    column_count: int
    columns: list[ColumnMeta]
    updated_at: datetime
    tags: list[str]

@dataclass(frozen=True)
class ColumnMeta:
    name: str
    dtype: str       # int64/float64/datetime64/string/category
    nullable: bool
    unit: str | None
    semantic: str | None  # timestamp/sensor_id/measurement/batch_id/...

@dataclass(frozen=True)
class QueryResult:
    df: pd.DataFrame
    row_count: int
    truncated: bool
    elapsed_ms: int
    cache_hit: bool

@dataclass(frozen=True)
class RepositoryHealth:
    available: bool
    latency_ms: int
    last_check: datetime
    backend_version: str | None
    notes: str | None
```

### Protocol

```python
@runtime_checkable
class DatasetRepository(Protocol):
    def list_datasets(self, *, user_id, tags=None) -> list[DatasetMeta]: ...
    def get_metadata(self, dataset_id, *, user_id) -> DatasetMeta: ...
    def execute_query(
        self, dataset_id, sql, *, user_id,
        max_rows=10_000_000, timeout_s=30,
    ) -> QueryResult: ...
    def get_value_at(
        self, dataset_id, *, user_id, column,
        index: dict[str, str],
    ) -> object: ...
    def health_check(self) -> RepositoryHealth: ...
```

### Errors (穩定型別)

```python
class RepositoryError(Exception): ...
class DatasetNotFoundError(RepositoryError): ...
class PermissionDeniedError(RepositoryError): ...
class QueryValidationError(RepositoryError): ...
class QueryTimeoutError(RepositoryError): ...
class QuerySizeError(RepositoryError): ...
class RepositoryUnavailableError(RepositoryError): ...
```

---

## Adapters

### HttpDatasetRepository (production)

`backend/open_webui/utils/data_analysis/adapters/http_adapter.py`

- `PROTOCOL_VERSION = "v1"` constant + `X-Protocol-Version` header
- `httpx.Client(base_url, headers, timeout)`
- 用 Apache Arrow IPC 傳大 DataFrame
- Retries (× 2), timeout 30s
- HTTP error code → vertical error mapping:
  - `DATASET_NOT_FOUND` → `DatasetNotFoundError`
  - `PERMISSION_DENIED` → `PermissionDeniedError`
  - `QUERY_INVALID` → `QueryValidationError`
  - `QUERY_TIMEOUT` → `QueryTimeoutError`
  - `QUERY_TOO_LARGE` → `QuerySizeError`
  - default → `RepositoryUnavailableError`
- DTO transformation in `_dataset_meta_from_dto(dto: dict) -> DatasetMeta`
- 不 retry user errors（DatasetNotFound、PermissionDenied 等）

### InMemoryDatasetRepository (tests / early dev)

`backend/open_webui/utils/data_analysis/adapters/in_memory_adapter.py`

- 持有 `dict[str, tuple[DatasetMeta, pd.DataFrame]]`
- Query：`pandasql` 或 `duckdb`
- 全部 method same Port API

#### Fault Injection（前端 error UI 測試用）

InMemory 偵測 SQL 內 magic string 自動觸發錯誤，前端不用改 mock：

| Magic string | 行為 |
|---|---|
| `_FAULT_TIMEOUT` | raise `QueryTimeoutError` |
| `_FAULT_NOT_FOUND` | raise `DatasetNotFoundError` |
| `_FAULT_DENIED` | raise `PermissionDeniedError` |
| `_FAULT_INVALID` | raise `QueryValidationError` |
| `_FAULT_TOO_LARGE` | raise `QuerySizeError` |
| `_FAULT_UNAVAILABLE` | raise `RepositoryUnavailableError` |
| `_FAULT_SLOW_3S` | `asyncio.sleep(3)` 後正常回 — 測 skeleton |
| `_FAULT_TRUNCATED` | 正常回但設 `truncated=True` |

**僅** InMemory adapter 啟用，HTTP adapter 透傳不解析。Production 不受影響。
詳見 [`database-adapter.md` §3.1](./database-adapter.md#31-fault-injection給前端測試-error-ui-用)。

### RecordReplayDatasetRepository (contract test 用)

包另一個 repo，第一次 record JSON 到 disk，後續 replay。CI 跑離線測試。

---

## Dependency Injection

```python
# backend/open_webui/utils/data_analysis/__init__.py

_repository: DatasetRepository | None = None

def get_repository() -> DatasetRepository:
    global _repository
    if _repository is not None:
        return _repository
    if DATA_ANALYSIS_REPOSITORY_TYPE == "http":
        from .adapters.http_adapter import HttpDatasetRepository
        _repository = HttpDatasetRepository(
            base_url=EXTERNAL_DATA_API_URL,
            service_token=EXTERNAL_DATA_API_TOKEN,
        )
    elif DATA_ANALYSIS_REPOSITORY_TYPE == "in_memory":
        from .adapters.in_memory_adapter import InMemoryDatasetRepository
        from .fixtures import LOCAL_FIXTURES
        _repository = InMemoryDatasetRepository(LOCAL_FIXTURES)
    return _repository

def set_repository(repo: DatasetRepository) -> None:
    """Test injection helper."""
    global _repository
    _repository = repo
```

---

## Configuration

```bash
# .env
DATA_ANALYSIS_REPOSITORY_TYPE=http   # http | in_memory | record_replay
EXTERNAL_DATA_API_URL=https://manufacturing-data.internal/api
EXTERNAL_DATA_API_TOKEN=<service-account-token>
EXTERNAL_DATA_API_TIMEOUT_S=30
EXTERNAL_DATA_API_RETRIES=2
```

---

## Tool function 用法

```python
from open_webui.utils.data_analysis import get_repository
from open_webui.utils.data_analysis.repository import (
    QueryValidationError, QueryTimeoutError, QuerySizeError,
    DatasetNotFoundError, PermissionDeniedError,
)

def query_dataset(dataset_id, query, max_rows=100, *, ctx) -> dict:
    repo = get_repository()
    try:
        result = repo.execute_query(
            dataset_id=dataset_id, sql=query,
            user_id=ctx.user_id, max_rows=10_000_000, timeout_s=30,
        )
    except DatasetNotFoundError:
        raise ToolError(f"Dataset {dataset_id} not found.")
    except PermissionDeniedError:
        raise ToolError(f"You don't have access to {dataset_id}.")
    except QueryValidationError as e:
        raise ToolError(f"Invalid query: {e}.")
    except QueryTimeoutError:
        raise ToolError("Query timed out (>30s).")
    # ...
```

Tool 不直接 import `httpx`，只 import abstract errors + DTOs。

---

## 三段進場路徑

| 階段 | Adapter | 對方系統 |
|---|---|---|
| Day 1–7 (vertical 自跑) | InMemory | 不需要 |
| Day 8–14 (mock server) | Http → mock | 對方 mock 端點 |
| Day 15+ (production) | Http → real | 對方完整 |

換 adapter = 改 `.env`，vertical 程式 0 改動。

---

## Protocol Versioning

對方升 v2 時：
1. 新建 `HttpDatasetRepositoryV2`，`PROTOCOL_VERSION = "v2"`
2. 透過 config 切換或灰度
3. **Port 不變** → vertical 內部 0 改動

---

## Manufacturing column semantic tags

`ColumnMeta.semantic` ∈：
```
'timestamp'    # 時序圖必要
'sensor_id'    # facet 候選
'batch_id'     # facet 候選
'sample_id'    # group_by 候選
'measurement'  # y-axis 候選
'spec_target'  # control/SPC 中心線
'spec_usl'     # 上控制限
'spec_lsl'     # 下控制限
'metadata'     # 通用描述
```

`render_chart` for `control`/`spc` MUST 先看 dataset 有沒有 `spec_target/usl/lsl`，否則 fallback `mean ± 3σ`。

---

## Contract test

```python
# tests/data_analysis/test_http_adapter_contract.py

@pytest.mark.contract
def test_list_datasets_dto_contract():
    repo = HttpDatasetRepository(STAGING_URL, STAGING_TOKEN)
    items = repo.list_datasets(user_id="test")
    assert all(isinstance(i, DatasetMeta) for i in items)
```

CI 階段對 staging 跑，確認對方 API 沒偷改。

---

## Acceptance

- [ ] `DatasetRepository` Protocol 完整定義（≥ 5 method）
- [ ] DTOs 全 `frozen=True`
- [ ] HTTP adapter：retry + timeout + error mapping
- [ ] InMemory adapter：全 method 實作，所有 unit test 用它
- [ ] `get_repository()` config-driven 切換
- [ ] Tool / route 程式 grep `import httpx` = 0 命中
- [ ] Contract test 至少 1 條對 staging 可跑
- [ ] Adapter `health_check` 整合 `/healthz`
- [ ] 外部系統 OpenAPI / proto file vendored 到 `docs/integration/`

---

## Anti-patterns

- ❌ Tool / route 內直接 `httpx.get(EXTERNAL_URL)` → 用 adapter
- ❌ Adapter 回 raw httpx response → 回 DTO
- ❌ Adapter 用 vertical 自定 model class → 用 DTO
- ❌ Monolithic `external_api.py` 函式庫 → Port + Adapter
- ❌ External error 直接 raise httpx exception → mapping 成 vertical error
- ❌ Adapter 內做 caching / business logic → adapter 是 thin transport，logic 在 vertical

---

## 跨檔關聯

- Tool 用法：[`tools-schema.brief.md`](./tools-schema.brief.md)
- Domain 欄位語意：[`data-analysis-vertical-spec.brief.md`](./data-analysis-vertical-spec.brief.md)
- 不依賴 event-ledger（兩個獨立系統）
