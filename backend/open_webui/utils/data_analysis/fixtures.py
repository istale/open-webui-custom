from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from open_webui.utils.data_analysis.repository import ColumnMeta, DatasetMeta


SENSOR_READINGS_COLUMNS = [
    ColumnMeta('timestamp', 'datetime64[ns]', False, None, 'timestamp'),
    ColumnMeta('sensor_id', 'string', False, None, 'sensor_id'),
    ColumnMeta('batch_id', 'string', False, None, 'batch_id'),
    ColumnMeta('line_id', 'string', False, None, 'metadata'),
    ColumnMeta('temperature_c', 'float64', False, 'celsius', 'measurement'),
    ColumnMeta('pressure_kpa', 'float64', False, 'kPa', 'measurement'),
    ColumnMeta('spec_target', 'float64', True, 'celsius', 'spec_target'),
    ColumnMeta('spec_usl', 'float64', True, 'celsius', 'spec_usl'),
    ColumnMeta('spec_lsl', 'float64', True, 'celsius', 'spec_lsl'),
]

BATCH_QUALITY_COLUMNS = [
    ColumnMeta('timestamp', 'datetime64[ns]', False, None, 'timestamp'),
    ColumnMeta('batch_id', 'string', False, None, 'batch_id'),
    ColumnMeta('sample_id', 'string', False, None, 'sample_id'),
    ColumnMeta('station_id', 'string', False, None, 'metadata'),
    ColumnMeta('diameter_mm', 'float64', False, 'mm', 'measurement'),
    ColumnMeta('roughness_ra', 'float64', False, 'um', 'measurement'),
    ColumnMeta('spec_target', 'float64', True, 'mm', 'spec_target'),
    ColumnMeta('spec_usl', 'float64', True, 'mm', 'spec_usl'),
    ColumnMeta('spec_lsl', 'float64', True, 'mm', 'spec_lsl'),
]


sensor_readings_df = pd.DataFrame(
    {
        'timestamp': pd.to_datetime(
            [
                '2026-05-01T08:00:00Z',
                '2026-05-01T08:01:00Z',
                '2026-05-01T08:02:00Z',
                '2026-05-01T08:03:00Z',
                '2026-05-01T08:04:00Z',
                '2026-05-01T08:05:00Z',
            ]
        ),
        'sensor_id': ['TEMP-01', 'TEMP-01', 'TEMP-02', 'TEMP-02', 'TEMP-03', 'TEMP-03'],
        'batch_id': ['B-1001', 'B-1001', 'B-1001', 'B-1002', 'B-1002', 'B-1002'],
        'line_id': ['LINE-A', 'LINE-A', 'LINE-A', 'LINE-B', 'LINE-B', 'LINE-B'],
        'temperature_c': [74.9, 75.1, 75.4, 76.2, 74.7, 75.0],
        'pressure_kpa': [210.2, 211.0, 209.8, 214.1, 208.9, 210.5],
        'spec_target': [75.0] * 6,
        'spec_usl': [77.0] * 6,
        'spec_lsl': [73.0] * 6,
    }
)

batch_quality_df = pd.DataFrame(
    {
        'timestamp': pd.to_datetime(
            [
                '2026-05-01T09:00:00Z',
                '2026-05-01T09:05:00Z',
                '2026-05-01T09:10:00Z',
                '2026-05-01T09:15:00Z',
                '2026-05-01T09:20:00Z',
            ]
        ),
        'batch_id': ['B-1001', 'B-1001', 'B-1002', 'B-1002', 'B-1003'],
        'sample_id': ['S-001', 'S-002', 'S-003', 'S-004', 'S-005'],
        'station_id': ['QC-1', 'QC-1', 'QC-2', 'QC-2', 'QC-3'],
        'diameter_mm': [10.01, 10.03, 9.98, 10.04, 10.00],
        'roughness_ra': [0.42, 0.39, 0.44, 0.41, 0.40],
        'spec_target': [10.0] * 5,
        'spec_usl': [10.05] * 5,
        'spec_lsl': [9.95] * 5,
    }
)


LOCAL_FIXTURES = {
    'sensor_readings': (
        DatasetMeta(
            id='sensor_readings',
            name='Line Sensor Readings',
            description='Minute-level manufacturing sensor readings with batch and spec context.',
            row_count=len(sensor_readings_df),
            column_count=len(SENSOR_READINGS_COLUMNS),
            columns=SENSOR_READINGS_COLUMNS,
            updated_at=datetime(2026, 5, 1, 8, 5, tzinfo=timezone.utc),
            tags=['manufacturing', 'sensors', 'line-a', 'line-b'],
        ),
        sensor_readings_df,
    ),
    'batch_quality': (
        DatasetMeta(
            id='batch_quality',
            name='Batch Quality Measurements',
            description='Sample-level quality measurements for manufactured batches.',
            row_count=len(batch_quality_df),
            column_count=len(BATCH_QUALITY_COLUMNS),
            columns=BATCH_QUALITY_COLUMNS,
            updated_at=datetime(2026, 5, 1, 9, 20, tzinfo=timezone.utc),
            tags=['manufacturing', 'quality', 'spc'],
        ),
        batch_quality_df,
    ),
}
