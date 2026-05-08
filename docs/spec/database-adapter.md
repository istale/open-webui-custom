# Database Adapter — 對接外部 Standalone 資料系統

> **背景**：Vertical workspace 不直接管理生產資料庫，原始 dataset / sensor 資料由**另一個 standalone 系統維護**（可能是 IT 既有的 manufacturing data platform、historian、data lake 等）。
>
> **目的**：在 vertical workspace 與外部系統之間定義一條**穩定、版本化、可換的整合介面**。
>
> **設計模式**：Hexagonal Architecture / Port & Adapter（也叫 Dependency Inversion / Repository pattern）。Vertical workspace 寫程式時依賴**抽象 interface (Port)**，實作 (Adapter) 可隨外部系統換版而換。

---

## 為什麼要這層

不寫 adapter 的代價：
- ❌ 整個 codebase 散落 `httpx.get(MANUFACTURING_API + ...)` → 對方 API 改版你要改 20 處
- ❌ 測試必須真的打外部系統，CI 慢、不穩、無法離線開發
- ❌ 換系統（從 Historian 換到 Time-Series DB）等於整個重寫
- ❌ 沒有 schema 邊界 → vertical 內部資料結構汙染進外部 API call

寫 adapter 的好處：
- ✅ 一個 `DatasetRepository` interface，N 個 implementation（HTTP / gRPC / local SQL / mock）
- ✅ 測試用 InMemory adapter，不打外部
- ✅ 對方 API 改版 = 改一個 adapter 檔案
- ✅ Schema 邊界明確（DTO transformation 都在 adapter 內）

---

## 名詞

| 名詞 | 意思 |
|---|---|
| **Port** | 抽象介面（Python `Protocol` 或 `ABC`），定義 vertical 需要的能力 |
| **Adapter** | Port 的具體實作，知道怎麼跟外部系統講話 |
| **DTO**（Data Transfer Object）| 跨邊界傳輸的資料形狀，與內部 domain object 分開 |
| **Domain Object** | Vertical 內部用的資料結構（pandas DataFrame、ChartSpec 等）|

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Vertical Workspace (your code, this repo)                        │
│                                                                   │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │  Tools           │    │  Routes          │                   │
│  │  - query_dataset │    │  - /datasets     │                   │
│  │  - render_chart  │    │  - /charts/...   │                   │
│  └────────┬─────────┘    └────────┬─────────┘                   │
│           │                       │                              │
│           └───────────┬───────────┘                              │
│                       │ uses                                     │
│                       ▼                                          │
│  ┌──────────────────────────────────────────────┐               │
│  │  Port (Protocol/ABC) — define what we need   │               │
│  │  class DatasetRepository:                    │               │
│  │    list_datasets() -> list[DatasetMeta]      │               │
│  │    get_metadata(id) -> DatasetMeta           │               │
│  │    execute_query(id, sql) -> DataFrame       │               │
│  │    ...                                       │               │
│  └─────────┬────────────────────────────────────┘               │
│            │ implemented by                                      │
│            ▼                                                     │
│  ┌──────────────────────────────────────────────┐               │
│  │  Adapter (production)                        │               │
│  │  HttpDatasetRepository(base_url, token)      │               │
│  │  - calls external system via REST/gRPC       │               │
│  │  - DTO ↔ Domain transformations              │               │
│  │  - retry / timeout / error mapping           │               │
│  └─────────┬────────────────────────────────────┘               │
│            │ HTTP/gRPC                                           │
└────────────┼─────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│ External Standalone System (NOT this repo)                       │
│  Manufacturing Data Platform / Historian / TS-DB                 │
└──────────────────────────────────────────────────────────────────┘
```

對應的測試 / 開發環境用：

```
┌─────────────────────┐
│  InMemoryAdapter    │ ← unit tests
├─────────────────────┤
│  LocalSqliteAdapter │ ← dev 環境，不需要連線
├─────────────────────┤
│  RecordReplayAdapter│ ← 錄一次 production response，replay 回放（contract test）
└─────────────────────┘
```

Vertical 程式碼**完全不知道**現在用的是哪個 adapter，靠 dependency injection 切換。

---

## 1. Port 定義（介面契約）

```python
# backend/open_webui/utils/data_analysis/repository.py

from __future__ import annotations
from typing import Protocol, runtime_checkable
from dataclasses import dataclass
from datetime import datetime
import pandas as pd


# ===== DTOs (跨邊界穩定形狀) =====

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
    dtype: str          # 'int64' / 'float64' / 'datetime64' / 'string' / 'category'
    nullable: bool
    unit: str | None    # 'celsius' / 'mmHg' / etc.
    semantic: str | None  # 'timestamp' / 'sensor_id' / 'measurement' / 'batch_id'

@dataclass(frozen=True)
class QueryResult:
    df: pd.DataFrame
    row_count: int
    truncated: bool       # True 表示因 size limit 被截斷
    elapsed_ms: int
    cache_hit: bool       # 來自外部系統 cache 還是 fresh query


# ===== Port (vertical 程式碼依賴這個介面) =====

@runtime_checkable
class DatasetRepository(Protocol):
    """Vertical workspace's contract with the external dataset system.

    Implementations MUST be:
    - Idempotent on read operations
    - Thread-safe
    - Stateless (no instance-level mutation between calls)
    """

    def list_datasets(self, *, user_id: str, tags: list[str] | None = None) -> list[DatasetMeta]:
        """List datasets visible to user_id, optionally filtered by tags."""

    def get_metadata(self, dataset_id: str, *, user_id: str) -> DatasetMeta:
        """Get full metadata. Raises DatasetNotFoundError / PermissionDeniedError."""

    def execute_query(
        self,
        dataset_id: str,
        sql: str,
        *,
        user_id: str,
        max_rows: int = 10_000_000,
        timeout_s: int = 30,
    ) -> QueryResult:
        """Run a SELECT query. Returns full DataFrame (caller decides downsampling).

        Raises:
          QueryValidationError — non-SELECT, syntax error
          QueryTimeoutError — exceeded timeout_s
          QuerySizeError — exceeded max_rows
          PermissionDeniedError — user_id lacks access
        """

    def get_value_at(
        self,
        dataset_id: str,
        *,
        user_id: str,
        column: str,
        index: dict[str, str],  # e.g. {"timestamp": "2024-10-01T00:00:00", "sensor_id": "S12"}
    ) -> object:
        """Point lookup, used for tooltips / drill-down."""

    def health_check(self) -> RepositoryHealth:
        """Return health of underlying system, used for dashboard."""


@dataclass(frozen=True)
class RepositoryHealth:
    available: bool
    latency_ms: int
    last_check: datetime
    backend_version: str | None
    notes: str | None


# ===== Errors (穩定的 vertical 端可 catch 的型別) =====

class RepositoryError(Exception): ...
class DatasetNotFoundError(RepositoryError): ...
class PermissionDeniedError(RepositoryError): ...
class QueryValidationError(RepositoryError): ...
class QueryTimeoutError(RepositoryError): ...
class QuerySizeError(RepositoryError): ...
class RepositoryUnavailableError(RepositoryError): ...
```

**為什麼用 `Protocol` 而非 `ABC`**：
- 結構化型別（duck typing）— 不強制繼承，第三方 adapter 也能 satisfy
- mypy / pyright 仍能靜態驗證
- 測試 mock 不用繼承

---

## 2. HTTP Adapter（Production 預設實作）

```python
# backend/open_webui/utils/data_analysis/adapters/http_adapter.py

import httpx
import pandas as pd
from io import BytesIO

from ..repository import (
    DatasetRepository, DatasetMeta, ColumnMeta, QueryResult, RepositoryHealth,
    DatasetNotFoundError, PermissionDeniedError, QueryValidationError,
    QueryTimeoutError, RepositoryUnavailableError
)


class HttpDatasetRepository:
    """Adapter for the external Manufacturing Data Platform via REST.

    External API spec: see docs/integration/manufacturing-data-api.md
    """

    PROTOCOL_VERSION = "v1"

    def __init__(self, base_url: str, service_token: str, *,
                 timeout_s: int = 30, retries: int = 2):
        self._client = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {service_token}",
                "X-Protocol-Version": self.PROTOCOL_VERSION,
            },
            timeout=timeout_s,
        )
        self._retries = retries

    # ----- vertical 端可看到的 API（Port 實作）-----

    def list_datasets(self, *, user_id: str, tags=None) -> list[DatasetMeta]:
        params = {"user_id": user_id}
        if tags:
            params["tags"] = ",".join(tags)
        resp = self._get("/datasets", params=params)
        return [self._dataset_meta_from_dto(item) for item in resp["items"]]

    def get_metadata(self, dataset_id: str, *, user_id: str) -> DatasetMeta:
        resp = self._get(f"/datasets/{dataset_id}", params={"user_id": user_id})
        return self._dataset_meta_from_dto(resp)

    def execute_query(self, dataset_id, sql, *, user_id,
                       max_rows=10_000_000, timeout_s=30) -> QueryResult:
        # Use Apache Arrow IPC for efficient large DataFrame transfer
        resp = self._post(
            f"/datasets/{dataset_id}/query",
            json={
                "sql": sql,
                "user_id": user_id,
                "max_rows": max_rows,
                "timeout_s": timeout_s,
                "format": "arrow",
            },
            stream=True,
        )
        df = pd.read_feather(BytesIO(resp.content))
        return QueryResult(
            df=df,
            row_count=int(resp.headers.get("X-Row-Count", len(df))),
            truncated=resp.headers.get("X-Truncated") == "true",
            elapsed_ms=int(resp.headers.get("X-Elapsed-Ms", 0)),
            cache_hit=resp.headers.get("X-Cache") == "hit",
        )

    def get_value_at(self, dataset_id, *, user_id, column, index) -> object:
        resp = self._get(
            f"/datasets/{dataset_id}/value",
            params={"user_id": user_id, "column": column, **index}
        )
        return resp["value"]

    def health_check(self) -> RepositoryHealth:
        try:
            resp = self._get("/healthz")
            return RepositoryHealth(
                available=True,
                latency_ms=resp["_elapsed_ms"],
                last_check=datetime.now(timezone.utc),
                backend_version=resp.get("version"),
                notes=None,
            )
        except RepositoryUnavailableError as e:
            return RepositoryHealth(
                available=False, latency_ms=-1,
                last_check=datetime.now(timezone.utc),
                backend_version=None, notes=str(e),
            )

    # ----- 內部：HTTP / DTO transform / error mapping -----

    def _get(self, path, **kwargs):
        return self._request("GET", path, **kwargs)

    def _post(self, path, **kwargs):
        return self._request("POST", path, **kwargs)

    def _request(self, method, path, **kwargs):
        last_exc = None
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.request(method, path, **kwargs)
                self._raise_for_external_error(resp)
                if kwargs.get("stream"):
                    return resp
                return resp.json()
            except httpx.TimeoutException as e:
                last_exc = QueryTimeoutError(f"External system timeout: {e}")
            except httpx.NetworkError as e:
                last_exc = RepositoryUnavailableError(f"Network error: {e}")
            except (DatasetNotFoundError, PermissionDeniedError, QueryValidationError):
                raise  # Don't retry user errors
        raise last_exc

    def _raise_for_external_error(self, resp: httpx.Response):
        if resp.status_code == 200:
            return
        try:
            err = resp.json()
        except Exception:
            err = {"code": "unknown", "message": resp.text}

        code = err.get("code", "unknown")
        msg = err.get("message", "External system error")
        mapping = {
            "DATASET_NOT_FOUND": DatasetNotFoundError,
            "PERMISSION_DENIED": PermissionDeniedError,
            "QUERY_INVALID": QueryValidationError,
            "QUERY_TIMEOUT": QueryTimeoutError,
            "QUERY_TOO_LARGE": QuerySizeError,
        }
        ExcCls = mapping.get(code, RepositoryUnavailableError)
        raise ExcCls(msg)

    @staticmethod
    def _dataset_meta_from_dto(dto: dict) -> DatasetMeta:
        return DatasetMeta(
            id=dto["id"],
            name=dto["name"],
            description=dto.get("description", ""),
            row_count=int(dto["row_count"]),
            column_count=int(dto["column_count"]),
            columns=[
                ColumnMeta(
                    name=c["name"],
                    dtype=c["dtype"],
                    nullable=c.get("nullable", True),
                    unit=c.get("unit"),
                    semantic=c.get("semantic"),
                )
                for c in dto["columns"]
            ],
            updated_at=datetime.fromisoformat(dto["updated_at"]),
            tags=dto.get("tags", []),
        )
```

---

## 3. InMemory Adapter（測試 / 早期 dev 用）

```python
# backend/open_webui/utils/data_analysis/adapters/in_memory_adapter.py

class InMemoryDatasetRepository:
    """Test / dev adapter — holds DataFrames in memory."""

    def __init__(self, datasets: dict[str, tuple[DatasetMeta, pd.DataFrame]]):
        self._data = datasets

    def list_datasets(self, *, user_id, tags=None):
        return [meta for meta, _ in self._data.values()
                if not tags or set(tags) & set(meta.tags)]

    def get_metadata(self, dataset_id, *, user_id):
        if dataset_id not in self._data:
            raise DatasetNotFoundError(f"{dataset_id}")
        return self._data[dataset_id][0]

    def execute_query(self, dataset_id, sql, *, user_id,
                       max_rows=10_000_000, timeout_s=30):
        if dataset_id not in self._data:
            raise DatasetNotFoundError(f"{dataset_id}")
        df = self._data[dataset_id][1]
        # Naive SQL via pandasql (or duckdb for production-ish testing)
        import pandasql
        result = pandasql.sqldf(sql, locals())
        if len(result) > max_rows:
            result = result.head(max_rows)
            truncated = True
        else:
            truncated = False
        return QueryResult(
            df=result, row_count=len(result),
            truncated=truncated, elapsed_ms=0, cache_hit=False
        )

    def get_value_at(self, dataset_id, *, user_id, column, index):
        df = self._data[dataset_id][1]
        mask = pd.Series([True] * len(df))
        for k, v in index.items():
            mask &= (df[k].astype(str) == v)
        return df.loc[mask, column].iloc[0]

    def health_check(self):
        return RepositoryHealth(
            available=True, latency_ms=0,
            last_check=datetime.now(timezone.utc),
            backend_version="in-memory", notes=None,
        )
```

---

## 4. Dependency Injection / Wiring

```python
# backend/open_webui/utils/data_analysis/__init__.py

from open_webui.config import (
    DATA_ANALYSIS_REPOSITORY_TYPE,  # "http" | "in_memory" | "sqlite"
    EXTERNAL_DATA_API_URL,
    EXTERNAL_DATA_API_TOKEN,
)

_repository: DatasetRepository | None = None

def get_repository() -> DatasetRepository:
    """Singleton accessor used by tools and routes."""
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
    else:
        raise ValueError(f"Unknown repo type: {DATA_ANALYSIS_REPOSITORY_TYPE}")

    return _repository

def set_repository(repo: DatasetRepository) -> None:
    """Test injection helper."""
    global _repository
    _repository = repo
```

工具 / route 都這樣呼叫：

```python
def query_dataset(dataset_id: str, query: str, ...) -> dict:
    repo = get_repository()
    result = repo.execute_query(dataset_id, query, user_id=ctx.user_id, ...)
    ...
```

**Vertical 內部完全不 import `httpx`**。換 adapter = 改 config，不動程式。

---

## 5. 與外部系統的契約管理

### 5.1 Protocol versioning

`HttpDatasetRepository.PROTOCOL_VERSION = "v1"` + `X-Protocol-Version` header。

對方升 v2 時：
1. 新建 `HttpDatasetRepositoryV2`，`PROTOCOL_VERSION = "v2"`
2. 透過 config 切換或灰度推進
3. `DatasetRepository` Port **不變** → vertical 內部零改動

### 5.2 Contract test

每個 release 跑 contract test 確認對方 API 沒偷偷改：

```python
# tests/data_analysis/test_http_adapter_contract.py

@pytest.mark.contract  # only run in CI against real staging
def test_list_datasets_dto_contract():
    repo = HttpDatasetRepository(STAGING_URL, STAGING_TOKEN)
    items = repo.list_datasets(user_id="test")
    assert all(isinstance(i, DatasetMeta) for i in items)
    assert all(i.id and i.name for i in items)
```

### 5.3 Record-Replay

開發時錄一次 staging response 存檔，CI 用 replay：

```python
class RecordReplayDatasetRepository:
    """Wraps another repo. First run records, subsequent runs replay from disk."""
    # ...
```

---

## 6. Vertical 端的使用範例（前面 tool calling 的銜接）

```python
# backend/open_webui/tools/data_analysis/query_dataset.py

from open_webui.utils.data_analysis import get_repository
from open_webui.utils.data_analysis.repository import (
    QueryValidationError, QueryTimeoutError, QuerySizeError,
    DatasetNotFoundError, PermissionDeniedError
)

def query_dataset(dataset_id: str, query: str, max_rows: int = 100, *, ctx) -> dict:
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
        raise ToolError(f"Invalid query: {e}. Only SELECT statements are allowed.")
    except QueryTimeoutError:
        raise ToolError("Query timed out (>30s). Try a more selective filter.")

    # Cache full df for downstream render_chart
    query_id = uuid4().hex
    query_cache.put(query_id, result.df, ttl_s=3600)

    return {
        "query_id": query_id,
        "row_count": result.row_count,
        "columns": [c for c in result.df.columns],
        "preview": result.df.head(max_rows).to_dict(orient="records"),
        ...
    }
```

注意：tool 程式碼**只認**抽象 errors + DTOs，看不到 HTTP / network 細節。

---

## 7. Configuration

```bash
# .env

# 切換 adapter
DATA_ANALYSIS_REPOSITORY_TYPE=http   # http | in_memory | record_replay

# HTTP adapter 設定
EXTERNAL_DATA_API_URL=https://manufacturing-data.internal/api
EXTERNAL_DATA_API_TOKEN=<service-account-token>
EXTERNAL_DATA_API_TIMEOUT_S=30
EXTERNAL_DATA_API_RETRIES=2
```

---

## 8. 當外部系統還沒 ready 時的開發路徑

開新 vertical 時，外部 standalone 系統可能還沒蓋好 / API 還沒定。三段式進場：

| 階段 | Adapter | 對方系統 |
|---|---|---|
| **Day 1–7（vertical 自己跑）** | `InMemoryDatasetRepository` + 預製 fixture | 不需要 |
| **Day 8–14（外部 stub 上線）** | `HttpDatasetRepository` 連 mock server | 對方提供 mock 端點 |
| **Day 15+（production）** | `HttpDatasetRepository` 連真 API | 對方完整 |

中間階段你的 vertical 程式碼**完全不變**，只換 config。

---

## 9. 反 pattern

| 反 pattern | 為什麼錯 |
|---|---|
| 在 tool / route 內直接 `httpx.get(EXTERNAL_URL)` | 散布 N 處，對方 API 改版要改 N 處 |
| Adapter 回傳 raw httpx response | 把外部 schema 洩進 vertical 內部 |
| Adapter 用 vertical 自己的 model class（如 `Card`）| 反向耦合，外部系統改 schema 影響 vertical model |
| 一個 monolithic `external_api.py` 函式庫 | 沒介面 = 沒法 mock，測試只能整套打外部 |
| 外部 error 直接 raise httpx.HTTPStatusError | Tool 端要 catch httpx exceptions 就違反邊界 |
| Adapter 內做 caching / business logic | Adapter 應該是 thin transport layer，business logic 在 vertical 內 |

---

## Acceptance Checklist

新 vertical 建好 adapter 後：

- [ ] `DatasetRepository` Protocol 定義完整，至少 4 個方法（list / get / execute / health）
- [ ] DTO 全部 `frozen=True` dataclass，跨邊界穩定
- [ ] HTTP adapter 寫完，含 retry / timeout / error mapping
- [ ] InMemory adapter 寫完，所有 unit test 用它
- [ ] `get_repository()` 透過 config 切換 adapter
- [ ] Tool / route 程式 0 處直接 `import httpx`
- [ ] Contract test 至少一條，能對 staging 跑
- [ ] Adapter 健康檢查整合進 `/healthz` route
- [ ] 文件記錄外部系統的 API contract 版本（vendored OpenAPI / proto file）
