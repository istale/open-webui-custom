from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / 'backend'
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('ENABLE_DB_MIGRATIONS', 'false')

from open_webui.utils.data_analysis import set_repository
from open_webui.utils.data_analysis.adapters.in_memory_adapter import InMemoryDatasetRepository
from open_webui.utils.data_analysis.eval import build_eval_cases, run_candidate
from open_webui.utils.data_analysis.fixtures import LOCAL_FIXTURES
from open_webui.utils.data_analysis.scoring import (
    score_candidate,
    summarize_eval_reports,
)


def _single_turn_traj() -> dict:
    return {
        'chat_id': 'c1',
        'user_id': 'u1',
        'session_events': [],
        'turns': [
            {
                'message_id': 'm1',
                'ts': 100,
                'user_prompt': 'plot the temperature trend',
                'request': {
                    'model': 'M',
                    'system_prompt': 'You are a manufacturing analyst.',
                    'message_count': 2,
                    'tool_ids': ['builtin:data-analysis'],
                    'params': {},
                },
                'thinking': [],
                'actions': [
                    {
                        'event_type': 'tool.query_dataset.succeeded',
                        'ts': 101,
                        'success': True,
                        'args': {'dataset_id': 'sensor_readings'},
                        'result': {'query_id': 'q-rec'},
                    },
                    {
                        'event_type': 'tool.render_chart.succeeded',
                        'ts': 102,
                        'success': True,
                        'args': {'x': 'timestamp', 'y': 'temperature_c', 'chart_type': 'line'},
                        'result': {'chart_id': 'ch-rec'},
                    },
                ],
                'outcome': {'usage': {}},
                'charts_rendered': ['ch-rec'],
                'charts_viewed': [],
                'reward': None,
            }
        ],
    }


def _case_dict(case) -> dict:
    return {'chat_id': case.chat_id, 'message_id': case.message_id, 'recorded': case.recorded}


def _run_dict(run) -> dict:
    return {'final_content': run.final_content, 'executed_calls': run.executed_calls, 'error': run.error}


# A faithful fake provider: drives query_dataset -> render_chart -> final answer,
# reading the running messages to chain on the live query_id and chart url.
async def _good_complete(*, messages, tools, params, model):
    last_tool = next((m for m in reversed(messages) if m.get('role') == 'tool'), None)
    if last_tool is None:
        return {
            'tool_calls': [
                {
                    'id': 'c1',
                    'name': 'query_dataset',
                    'arguments': {
                        'dataset_id': 'sensor_readings',
                        'query': 'SELECT timestamp, temperature_c FROM df ORDER BY timestamp',
                    },
                }
            ],
            'content': None,
        }
    data = json.loads(last_tool['content'])
    if 'attachment' in data:  # render_chart result
        url = data['attachment']['url']
        return {'tool_calls': [], 'content': f"Here is the trend ![t]({url})"}
    if 'query_id' in data:
        return {
            'tool_calls': [
                {
                    'id': 'c2',
                    'name': 'render_chart',
                    'arguments': {
                        'query_id': data['query_id'],
                        'chart_type': 'line',
                        'x': 'timestamp',
                        'y': 'temperature_c',
                    },
                }
            ],
            'content': None,
        }
    return {'tool_calls': [], 'content': 'done'}


# A freelancing fake: never calls a tool, just answers in prose.
async def _freelance_complete(*, messages, tools, params, model):
    return {'tool_calls': [], 'content': 'Here is some python: df.plot()'}


def test_build_eval_cases_gates_to_single_turn():
    traj = _single_turn_traj()
    cases = build_eval_cases(traj)
    assert len(cases) == 1
    assert cases[0].user_prompt == 'plot the temperature trend'
    assert cases[0].recorded['used_tools'] is True
    assert cases[0].recorded['render_succeeded'] is True

    # message_count > 2 => not evaluable (multi-turn gate).
    traj['turns'][0]['request']['message_count'] = 6
    assert build_eval_cases(traj) == []


def test_good_candidate_passes_against_baseline():
    async def run():
        set_repository(InMemoryDatasetRepository(LOCAL_FIXTURES))
        try:
            case = build_eval_cases(_single_turn_traj())[0]
            run_res = await run_candidate(
                case,
                InMemoryDatasetRepository(LOCAL_FIXTURES),
                complete=_good_complete,
            )
        finally:
            set_repository(None)

        names = [c['name'] for c in run_res.executed_calls]
        assert names == ['query_dataset', 'render_chart']
        assert all(c['success'] for c in run_res.executed_calls)

        report = score_candidate(_case_dict(case), _run_dict(run_res))
        assert report['checks']['used_tools']['candidate'] is True
        assert report['checks']['render_succeeded']['candidate'] is True
        assert report['checks']['embedded_real_url']['candidate'] is True
        assert report['checks']['tool_workflow_ok']['candidate'] is True
        assert report['regressed_checks'] == []
        assert report['passed'] is True

        verdict = summarize_eval_reports([report])
        assert verdict['passed'] is True
        assert verdict['cases'] == 1

    asyncio.run(run())


def test_freelancing_candidate_regresses():
    async def run():
        set_repository(InMemoryDatasetRepository(LOCAL_FIXTURES))
        try:
            case = build_eval_cases(_single_turn_traj())[0]
            run_res = await run_candidate(
                case,
                InMemoryDatasetRepository(LOCAL_FIXTURES),
                complete=_freelance_complete,
            )
        finally:
            set_repository(None)

        assert run_res.executed_calls == []
        report = score_candidate(_case_dict(case), _run_dict(run_res))
        # Baseline used tools + rendered; candidate did neither => regression.
        assert 'used_tools' in report['regressed_checks']
        assert 'render_succeeded' in report['regressed_checks']
        assert report['passed'] is False

        verdict = summarize_eval_reports([report])
        assert verdict['passed'] is False
        assert verdict['regressed_cases'] == 1

    asyncio.run(run())
