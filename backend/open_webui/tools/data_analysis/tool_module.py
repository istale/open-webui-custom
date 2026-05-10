"""Manufacturing data-analysis tools exposed through Open WebUI native chat.

Open WebUI discovers methods on ``class Tools`` and builds the model-visible
function schema from type hints plus docstrings. Keep infrastructure fields
such as user id, timestamps, cache keys, and chart ids out of method
parameters; native middleware injects ``__user__`` after the model chooses a
tool call.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from open_webui.utils.data_analysis import get_repository
from open_webui.utils.data_analysis.repository import DatasetMeta, RepositoryError


def _json_ready(value: Any) -> Any:
    """Convert frozen DTOs to JSON-ready values without adding model-visible fields."""
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _dataset_to_response(meta: DatasetMeta) -> dict[str, Any]:
    return _json_ready(meta)


class Tools:
    """Data analysis vertical workspace tools for manufacturing datasets."""

    def __init__(self):
        self.repo = get_repository()

    def list_datasets(self, tags: str = '', __user__: dict | None = None) -> dict[str, Any]:
        """List manufacturing datasets the current user can access.

        :param tags: Optional comma-separated tag filter, for example "production,line-a".
        :return: JSON object with schema_version and an items list of dataset metadata.
        """
        if not __user__ or not __user__.get('id'):
            raise ValueError('Authenticated user context is required to list datasets.')

        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()] or None

        try:
            items = self.repo.list_datasets(user_id=__user__['id'], tags=tag_list)
        except RepositoryError:
            raise
        except Exception as exc:
            raise RuntimeError(f'Unable to list manufacturing datasets: {exc}') from exc

        return {
            'schema_version': 1,
            'items': [_dataset_to_response(item) for item in items],
        }
