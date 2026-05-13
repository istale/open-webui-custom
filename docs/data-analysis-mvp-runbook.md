# Data Analysis MVP Runbook

This runbook explains how to start and verify the manufacturing data-analysis vertical delivered through CP-7.

## What This Vertical Adds

The vertical is intentionally small:

- Backend tools are native Open WebUI tools under `backend/open_webui/tools/data_analysis/`.
- Data access goes through `DatasetRepository`; tool code does not import `httpx`.
- Charts are rendered server-side with Matplotlib and served from `/api/v1/data-analysis/charts/{chart_id}.png`.
- Frontend lives at `/workspace/data-analysis` and reuses native `<Chat>`.
- Canvas cards are derived from native assistant `history.messages[].output[]` function-call output.
- Event analytics are written through the data-analysis event ledger worker.

## Required Environment

Use the normal Open WebUI environment plus:

```bash
# Optional. If unset, the InMemory repository is used.
EXTERNAL_DATA_API_URL=

# Required for production-scale Arrow/Feather parsing.
# Keep pyarrow and numpy pinned to a compatible pair before staging.
```

Important production note: local CP runs still show the known pyarrow / NumPy 2.x binary warning. The JSON/local fallback is acceptable for MVP verification only. Production workloads that approach 1M-10M rows must run with a compatible `pyarrow` and `numpy` pair.

## Backend Startup

Open WebUI already owns process startup. The vertical adds small hooks only:

- Tool registration in FastAPI lifespan.
- Event worker start/stop in FastAPI lifespan.
- Data-analysis router include for datasets, chart PNGs, and frontend event emits.

For local backend validation:

```bash
cd /Users/istale/Documents/open-webui-based-project
pytest tests/data_analysis/ -v
grep -rn "import httpx" backend/open_webui/tools backend/open_webui/routers
```

Expected:

```text
54 passed
<no grep output>
```

## Frontend Startup

Use Node 22 for this fork. The system Node 25 can fail package engine checks.

```bash
cd /Users/istale/Documents/open-webui-based-project
PATH=/usr/local/bin:$PATH npm ci
PATH=/usr/local/bin:$PATH npx vite dev --host 127.0.0.1 --port 5173
```

Smoke test:

```bash
curl -sS -I http://127.0.0.1:5173/workspace/data-analysis
```

Expected:

```text
HTTP/1.1 200 OK
x-sveltekit-page: true
```

## Database Migrations

The event ledger migration is part of the backend migration set:

- `backend/open_webui/migrations/versions/e5f6a7b8c9d0_add_data_analysis_events.py`

Run migrations the same way this Open WebUI deployment already runs Alembic migrations. Do not run a separate vertical migration command.

## Manual QA Script

CP-7 uses `docs/handoffs/artifacts/cp7-happy-path.json` as the durable evidence file for the core happy path:

1. List manufacturing datasets.
2. Read the `sensor_readings` schema.
3. Query timestamp, temperature, and spec-limit columns.
4. Render a control chart through `render_chart`.
5. Verify PNG and thumbnail files exist.
6. Verify reload behavior in the same backend process by checking the persisted chart file path.
7. Verify active branch behavior excludes sibling assistant messages.

The generated chart artifact is:

- `docs/handoffs/artifacts/cp7-temperature-control.png`
- `docs/handoffs/artifacts/cp7-temperature-control.thumb.png`

## Known MVP Limits

- Chart metadata is still in-process. Horizontal production deployment needs DB-backed chart metadata and S3/GCS-style object storage.
- Full repo-wide `npm run check` fails on existing Open WebUI type debt outside the vertical files. CP-7 verifies a filtered diagnostic pass for the vertical files.
- Live prompt-to-tool QA requires a configured model provider and authenticated browser session. CP-7 validates the native tool sequence and frontend render contract with deterministic local fixtures.
