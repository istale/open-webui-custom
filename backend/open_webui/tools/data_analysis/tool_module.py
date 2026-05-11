"""Manufacturing data-analysis tools exposed through Open WebUI native chat.

Open WebUI discovers methods on ``class Tools`` and builds the model-visible
function schema from type hints plus docstrings. Keep infrastructure fields
such as user id, timestamps, cache keys, and chart ids out of method
parameters; native middleware injects ``__user__`` after the model chooses a
tool call.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from open_webui.utils.data_analysis import get_repository
from open_webui.utils.data_analysis.chart_renderer import render_matplotlib_chart
from open_webui.utils.data_analysis.chart_store import ChartRecord, get_chart_store
from open_webui.utils.data_analysis.query_cache import get_query_cache
from open_webui.utils.data_analysis.repository import DatasetMeta, QueryResult, RepositoryError


def _json_ready(value: Any) -> Any:
    """Convert frozen DTOs to JSON-ready values without adding model-visible fields."""
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, 'isoformat') and value.__class__.__module__.startswith('pandas'):
        return value.isoformat()
    if hasattr(value, 'item') and value.__class__.__module__.startswith('numpy'):
        return _json_ready(value.item())
    if value != value:
        return None
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _dataset_to_response(meta: DatasetMeta) -> dict[str, Any]:
    return _json_ready(meta)


def _require_user(__user__: dict | None) -> str:
    if not __user__ or not __user__.get('id'):
        raise ValueError('Authenticated user context is required for data analysis tools.')
    return __user__['id']


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


def _statistics_for_df(df) -> dict[str, Any]:
    numeric = df.select_dtypes(include='number')
    stats: dict[str, Any] = {}
    for column in numeric.columns:
        series = numeric[column].dropna()
        if series.empty:
            continue
        stats[column] = _json_ready(
            {
                'count': int(series.count()),
                'mean': series.mean(),
                'std': series.std(),
                'min': series.min(),
                'max': series.max(),
            }
        )
    return stats


def _preview_from_result(result: QueryResult, max_rows: int) -> list[dict[str, Any]]:
    preview = result.df.head(max_rows).to_dict(orient='records')
    return _json_ready(preview)


class Tools:
    """Data analysis vertical workspace tools for manufacturing datasets."""

    def __init__(self):
        self.repo = get_repository()
        self.query_cache = get_query_cache()
        self.chart_store = get_chart_store()

    def list_datasets(self, tags: str = '', __user__: dict | None = None) -> dict[str, Any]:
        """List manufacturing datasets the current user can access.

        :param tags: Optional comma-separated tag filter, for example "production,line-a".
        :return: JSON object with schema_version and an items list of dataset metadata.
        """
        user_id = _require_user(__user__)

        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()] or None

        try:
            items = self.repo.list_datasets(user_id=user_id, tags=tag_list)
        except RepositoryError:
            raise
        except Exception as exc:
            raise RuntimeError(f'Unable to list manufacturing datasets: {exc}') from exc

        return {
            'schema_version': 1,
            'items': [_dataset_to_response(item) for item in items],
        }

    def get_dataset_schema(self, dataset_id: str, __user__: dict | None = None) -> dict[str, Any]:
        """Get column schema and metadata for a manufacturing dataset.

        :param dataset_id: Dataset identifier from list_datasets.
        :return: JSON object with dataset metadata and column schema.
        """
        user_id = _require_user(__user__)
        meta = self.repo.get_metadata(dataset_id, user_id=user_id)
        return {'schema_version': 1, 'dataset': _dataset_to_response(meta)}

    def query_dataset(
        self,
        dataset_id: str,
        query: str,
        max_rows: int = 100,
        __user__: dict | None = None,
    ) -> dict[str, Any]:
        """Run a SELECT query and cache the full result server-side.

        :param dataset_id: Dataset identifier from list_datasets.
        :param query: SQL SELECT statement. Non-SELECT statements are rejected by the repository.
        :param max_rows: Maximum preview rows to return to the model.
        :return: JSON object with query_id, row_count, preview rows, dtypes, and statistics.
        """
        user_id = _require_user(__user__)
        preview_rows = max(1, min(int(max_rows or 100), 500))
        result = self.repo.execute_query(
            dataset_id,
            query,
            user_id=user_id,
            max_rows=10_000_000,
            timeout_s=30,
        )
        query_id = self.query_cache.put(
            dataset_id=dataset_id,
            sql=query,
            df=result.df,
            user_id=user_id,
            row_count=result.row_count,
            ttl_s=3600,
        )
        return {
            'schema_version': 1,
            'query_id': query_id,
            'dataset_id': dataset_id,
            'row_count': result.row_count,
            'truncated': result.truncated,
            'elapsed_ms': result.elapsed_ms,
            'columns': list(result.df.columns),
            'dtypes': {column: str(dtype) for column, dtype in result.df.dtypes.items()},
            'preview': _preview_from_result(result, preview_rows),
            'statistics': _statistics_for_df(result.df),
        }

    def render_chart(
        self,
        query_id: str,
        chart_type: str,
        x: str,
        y: str,
        title: str,
        explanation_source: str,
        explanation_method: str,
        explanation_fields: str,
        facet: str = '',
        color: str = '',
        explanation_aggregation: str = '',
        explanation_notes: str = '',
        __user__: dict | None = None,
        __metadata__: dict | None = None,
    ) -> dict[str, Any]:
        """Render a matplotlib PNG from a cached query result.

        :param query_id: query_id returned by query_dataset.
        :param chart_type: One of line, bar, scatter, histogram, box, heatmap, control, spc, pareto.
        :param x: Column name for the x-axis or grouping axis.
        :param y: Column name for the y-axis or measured value.
        :param title: Chart title.
        :param explanation_source: Data source description for the analyst-facing caption.
        :param explanation_method: Statistical or aggregation method used.
        :param explanation_fields: Comma-separated column names referenced in the chart.
        :param facet: Optional grouping column reserved for future subplot support.
        :param color: Optional numeric column for scatter color or heatmap value.
        :param explanation_aggregation: Optional aggregation label.
        :param explanation_notes: Optional notes for analyst audit.
        :return: JSON object describing the rendered chart image attachment.
        """
        user_id = _require_user(__user__)
        entry = self.query_cache.get(query_id, user_id=user_id)
        if entry is None:
            raise ValueError(f'query_id {query_id} expired or not found. Please re-run query_dataset.')

        chart_id = uuid4().hex
        image_path, thumb_path = self.chart_store.paths_for(chart_id)
        render_info = render_matplotlib_chart(
            entry.df,
            chart_type=chart_type,
            x=x,
            y=y,
            title=title,
            output_path=image_path,
            thumb_path=thumb_path,
            facet=facet,
            color=color,
        )
        chat_id = (__metadata__ or {}).get('chat_id')
        self.chart_store.put(
            ChartRecord(
                chart_id=chart_id,
                user_id=user_id,
                path=image_path,
                thumb_path=thumb_path,
                chart_type=render_info['chart_type'],
                title=title,
                query_id=query_id,
                chat_id=chat_id,
            )
        )

        return {
            'schema_version': 1,
            'type': 'image',
            'attachment': {
                'id': chart_id,
                'url': f'/api/v1/data-analysis/charts/{chart_id}.png',
                'thumb_url': f'/api/v1/data-analysis/charts/{chart_id}.png?thumb=1',
                'mime_type': 'image/png',
                'metadata': {
                    'chart_type': render_info['chart_type'],
                    'title': title,
                    'explanation': {
                        'source': explanation_source,
                        'method': explanation_method,
                        'fields': _parse_csv(explanation_fields),
                        'aggregation': explanation_aggregation or None,
                        'notes': explanation_notes or None,
                        'statistics': _statistics_for_df(entry.df[[column for column in [x, y, color] if column]]),
                    },
                    'audit': {
                        'rendered_at': datetime.now(timezone.utc).isoformat(),
                        'renderer': 'matplotlib',
                        'raw_row_count': render_info['raw_row_count'],
                        'query_id': query_id,
                        'image_size_bytes': render_info['image_size_bytes'],
                    },
                },
            },
        }

    def summarize_data(
        self,
        query_id: str,
        title: str,
        summary: str,
        key_findings: str = '',
        __user__: dict | None = None,
    ) -> dict[str, Any]:
        """Package a textual summary of a cached query result.

        :param query_id: query_id returned by query_dataset.
        :param title: Summary title.
        :param summary: Markdown-formatted summary.
        :param key_findings: Optional newline- or semicolon-separated finding list.
        :return: JSON object with summary content and query audit context.
        """
        user_id = _require_user(__user__)
        entry = self.query_cache.get(query_id, user_id=user_id)
        if entry is None:
            raise ValueError(f'query_id {query_id} expired or not found. Please re-run query_dataset.')

        findings = [item.strip('- ').strip() for item in key_findings.replace(';', '\n').splitlines() if item.strip()]
        return {
            'schema_version': 1,
            'type': 'summary',
            'title': title,
            'summary': summary,
            'key_findings': findings,
            'metadata': {
                'query_id': query_id,
                'dataset_id': entry.dataset_id,
                'row_count': entry.row_count,
            },
        }
