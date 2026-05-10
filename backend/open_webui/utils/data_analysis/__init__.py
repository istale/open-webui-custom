from __future__ import annotations

import os

from open_webui.utils.data_analysis.repository import DatasetRepository

_repository: DatasetRepository | None = None


def get_repository() -> DatasetRepository:
    """Return the configured data-analysis repository singleton."""
    global _repository
    if _repository is not None:
        return _repository

    repository_type = os.getenv('DATA_ANALYSIS_REPOSITORY_TYPE', 'in_memory')
    if repository_type == 'http':
        from open_webui.utils.data_analysis.adapters.http_adapter import HttpDatasetRepository

        _repository = HttpDatasetRepository(
            base_url=os.getenv('EXTERNAL_DATA_API_URL', ''),
            service_token=os.getenv('EXTERNAL_DATA_API_TOKEN', ''),
            timeout_s=int(os.getenv('EXTERNAL_DATA_API_TIMEOUT_S', '30')),
            retries=int(os.getenv('EXTERNAL_DATA_API_RETRIES', '2')),
        )
    elif repository_type == 'in_memory':
        from open_webui.utils.data_analysis.adapters.in_memory_adapter import InMemoryDatasetRepository
        from open_webui.utils.data_analysis.fixtures import LOCAL_FIXTURES

        _repository = InMemoryDatasetRepository(LOCAL_FIXTURES)
    else:
        raise ValueError(f'Unknown data analysis repository type: {repository_type}')

    return _repository


def set_repository(repo: DatasetRepository | None) -> None:
    """Test injection helper; pass None to reset lazy construction."""
    global _repository
    _repository = repo
