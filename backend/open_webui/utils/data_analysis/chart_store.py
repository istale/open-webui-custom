from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from open_webui.env import DATA_DIR

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChartRecord:
    chart_id: str
    user_id: str
    path: Path
    thumb_path: Path
    chart_type: str
    title: str
    query_id: str
    chat_id: str | None = None


class ChartStore:
    """Durable chart registry plus stable file paths for rendered PNGs.

    Records are cached in-process for speed and persisted as a JSON sidecar
    (``{chart_id}.json``) next to the PNG. The sidecar lets chart metadata
    survive a backend restart and be shared across multiple workers that mount
    the same ``DATA_DIR`` filesystem — the PNG bytes were already durable, only
    the access-control / lookup metadata used to live solely in memory.
    """

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir or (DATA_DIR / 'cache')) / 'data_analysis' / 'charts'
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, ChartRecord] = {}
        self._lock = RLock()

    def paths_for(self, chart_id: str) -> tuple[Path, Path]:
        return self.base_dir / f'{chart_id}.png', self.base_dir / f'{chart_id}.thumb.png'

    def _sidecar_path(self, chart_id: str) -> Path:
        return self.base_dir / f'{chart_id}.json'

    def _write_sidecar(self, record: ChartRecord) -> None:
        sidecar = self._sidecar_path(record.chart_id)
        tmp = sidecar.with_suffix('.json.tmp')
        data = {
            'chart_id': record.chart_id,
            'user_id': record.user_id,
            'path': str(record.path),
            'thumb_path': str(record.thumb_path),
            'chart_type': record.chart_type,
            'title': record.title,
            'query_id': record.query_id,
            'chat_id': record.chat_id,
        }
        try:
            tmp.write_text(json.dumps(data))
            tmp.replace(sidecar)  # atomic on POSIX
        except OSError as e:
            log.warning('chart sidecar write failed for %s: %s', record.chart_id, e)

    def _read_sidecar(self, chart_id: str) -> ChartRecord | None:
        sidecar = self._sidecar_path(chart_id)
        if not sidecar.exists():
            return None
        try:
            data = json.loads(sidecar.read_text())
            return ChartRecord(
                chart_id=data['chart_id'],
                user_id=data['user_id'],
                path=Path(data['path']),
                thumb_path=Path(data['thumb_path']),
                chart_type=data['chart_type'],
                title=data['title'],
                query_id=data['query_id'],
                chat_id=data.get('chat_id'),
            )
        except (OSError, ValueError, KeyError) as e:
            log.warning('chart sidecar read failed for %s: %s', chart_id, e)
            return None

    def put(self, record: ChartRecord) -> None:
        with self._lock:
            self._records[record.chart_id] = record
        self._write_sidecar(record)

    def get(self, chart_id: str) -> ChartRecord | None:
        with self._lock:
            record = self._records.get(chart_id)
            if record is not None:
                return record
        # Cache miss — fall back to the durable sidecar (restart / other worker).
        record = self._read_sidecar(chart_id)
        if record is not None:
            with self._lock:
                self._records.setdefault(chart_id, record)
        return record

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


_chart_store = ChartStore()


def get_chart_store() -> ChartStore:
    return _chart_store
