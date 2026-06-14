from __future__ import annotations

P0_EVENT_FIXTURES: list[dict] = [
    {
        'event_type': 'workspace.opened',
        'payload': {'entry_path': 'sidebar'},
    },
    {
        'event_type': 'dataset.selected',
        'dataset_id': 'sensor_readings',
        'payload': {'dataset_id': 'sensor_readings', 'prev_dataset_id': None, 'from': 'row'},
    },
    {
        'event_type': 'prompt.submitted',
        'payload': {'prompt_text': 'show monthly trend', 'prompt_length': 18, 'model': 'test', 'is_first_in_chat': True},
    },
    {
        'event_type': 'model.thinking_completed',
        'duration_ms': 120,
        'payload': {'thinking_text': 'Need query then chart.', 'n_chars': 22},
    },
    {
        'event_type': 'tool.query_dataset.succeeded',
        'dataset_id': 'sensor_readings',
        'tool_name': 'query_dataset',
        'duration_ms': 42,
        'payload': {'sql': 'SELECT * FROM df', 'query_id': 'q1', 'row_count': 6, 'truncated': False},
    },
    {
        'event_type': 'tool.query_dataset.failed',
        'dataset_id': 'sensor_readings',
        'tool_name': 'query_dataset',
        'duration_ms': 42,
        'success': False,
        'error_code': 'QUERY_TIMEOUT',
        'payload': {'sql': 'SELECT * FROM df', 'error_message': 'timeout'},
    },
    {
        'event_type': 'tool.render_chart.succeeded',
        'chart_type': 'line',
        'tool_name': 'render_chart',
        'duration_ms': 90,
        'payload': {'chart_type': 'line', 'query_id': 'q1', 'chart_id': 'c1', 'image_size_bytes': 1000, 'statistics': {}},
    },
    {
        'event_type': 'tool.render_chart.failed',
        'chart_type': 'line',
        'tool_name': 'render_chart',
        'duration_ms': 90,
        'success': False,
        'error_code': 'QUERY_ID_NOT_FOUND',
        'payload': {'chart_type': 'line', 'error_message': 'query_id expired'},
    },
    {
        'event_type': 'chart.rendered',
        'chart_type': 'line',
        'payload': {'chart_id': 'c1', 'chart_type': 'line', 'displayed_in': 'canvas-card'},
    },
    {
        'event_type': 'message.assistant_completed',
        'message_id': 'm1',
        'duration_ms': 300,
        'payload': {'message_id': 'm1', 'total_duration_ms': 300, 'tool_call_count': 2, 'n_chars': 120, 'had_thinking': True},
    },
    {
        'event_type': 'stream.timeout',
        'chat_id': 'chat1',
        'duration_ms': 30_000,
        'payload': {'chat_id': 'chat1', 'elapsed_ms': 30_000, 'last_event_type': 'delta'},
    },
    {
        'event_type': 'stream.aborted',
        'chat_id': 'chat1',
        'payload': {'chat_id': 'chat1', 'reason': 'user-cancel'},
    },
    {
        'event_type': 'followup.clicked',
        'message_id': 'm1',
        'payload': {'followup_text': 'Show SPC chart', 'source_message_id': 'm1', 'followup_index': 0},
    },
]
