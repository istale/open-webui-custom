from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from open_webui.env import DATA_DIR


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
    """In-process chart registry plus stable file paths for rendered PNGs."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir or (DATA_DIR / 'cache')) / 'data_analysis' / 'charts'
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, ChartRecord] = {}
        self._lock = RLock()

    def paths_for(self, chart_id: str) -> tuple[Path, Path]:
        return self.base_dir / f'{chart_id}.png', self.base_dir / f'{chart_id}.thumb.png'

    def put(self, record: ChartRecord) -> None:
        with self._lock:
            self._records[record.chart_id] = record

    def get(self, chart_id: str) -> ChartRecord | None:
        with self._lock:
            return self._records.get(chart_id)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


_chart_store = ChartStore()


def get_chart_store() -> ChartStore:
    return _chart_store
