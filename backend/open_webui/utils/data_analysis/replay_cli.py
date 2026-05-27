"""CLI to close the interaction-replay loop (Phase 4).

Run from the backend dir:

    python -m open_webui.utils.data_analysis.replay_cli export    --out traj.jsonl [--since-days N] [--redact]
    python -m open_webui.utils.data_analysis.replay_cli regression [--since-days N]
    python -m open_webui.utils.data_analysis.replay_cli report     [--since-days N]
    python -m open_webui.utils.data_analysis.replay_cli eval       [--prompt-version V] [--model M] [--since-days N]

- export:     write trajectory records (one JSON object per line) for eval/training.
- regression: replay every trajectory's recorded tool calls deterministically and
              diff vs. recorded outcomes; exit code 1 if anything diverged (CI gate).
- report:     print aggregate analytics (failure clustering, retry rate, etc.).
- eval:       LLM-in-the-loop — re-run each evaluable single-turn case's input against
              a candidate prompt/model and score vs. the recorded baseline; exit code 1
              if the candidate regresses any rule-based check (A/B gate). Needs a live
              endpoint (MINIMAX_BASE_URL / MINIMAX_API_KEY).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time


def _since_ts(since_days: int | None) -> int | None:
    if not since_days:
        return None
    return int((time.time() - since_days * 86400) * 1000)


async def _cmd_export(args) -> int:
    from open_webui.utils.data_analysis.replay import export_trajectories

    trajs = await export_trajectories(since_ts=_since_ts(args.since_days), redact=args.redact)
    with open(args.out, 'w', encoding='utf-8') as fh:
        for traj in trajs:
            fh.write(json.dumps(traj, ensure_ascii=False, default=str) + '\n')
    print(f'exported {len(trajs)} trajectories -> {args.out}')
    return 0


async def _cmd_regression(args) -> int:
    from open_webui.utils.data_analysis import get_repository
    from open_webui.utils.data_analysis.analytics import summarize_replay_reports
    from open_webui.utils.data_analysis.replay import export_trajectories, replay_trajectory

    trajs = await export_trajectories(since_ts=_since_ts(args.since_days))
    repo = get_repository()
    reports = [replay_trajectory(t, repo) for t in trajs]
    verdict = summarize_replay_reports(reports)
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0 if verdict['passed'] else 1


async def _cmd_report(args) -> int:
    from open_webui.utils.data_analysis.analytics import summarize_trajectories
    from open_webui.utils.data_analysis.replay import export_trajectories

    trajs = await export_trajectories(since_ts=_since_ts(args.since_days))
    print(json.dumps(summarize_trajectories(trajs), indent=2, ensure_ascii=False))
    return 0


async def _cmd_eval(args) -> int:
    from open_webui.utils.data_analysis import get_repository
    from open_webui.utils.data_analysis.eval import build_eval_cases, run_candidate
    from open_webui.utils.data_analysis.llm_client import complete
    from open_webui.utils.data_analysis.replay import export_trajectories
    from open_webui.utils.data_analysis.scoring import score_candidate, summarize_eval_reports

    candidate_system = None
    if args.candidate_prompt_file:
        with open(args.candidate_prompt_file, encoding='utf-8') as fh:
            candidate_system = fh.read()

    trajs = await export_trajectories(since_ts=_since_ts(args.since_days))
    repo = get_repository()

    reports = []
    for traj in trajs:
        for case in build_eval_cases(traj):
            run = await run_candidate(
                case,
                repo,
                complete=complete,
                candidate_system=candidate_system,
                candidate_model=args.model,
            )
            reports.append(score_candidate(_case_dict(case), _run_dict(run)))

    verdict = summarize_eval_reports(reports)
    verdict['prompt_version'] = args.prompt_version
    verdict['model'] = args.model
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0 if verdict['passed'] else 1


def _case_dict(case) -> dict:
    return {'chat_id': case.chat_id, 'message_id': case.message_id, 'recorded': case.recorded}


def _run_dict(run) -> dict:
    return {'final_content': run.final_content, 'executed_calls': run.executed_calls, 'error': run.error}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='replay_cli')
    parser.add_argument('--since-days', type=int, default=None, help='retention window in days')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_export = sub.add_parser('export')
    p_export.add_argument('--out', default='trajectories.jsonl')
    p_export.add_argument('--redact', action='store_true')
    p_export.set_defaults(func=_cmd_export)

    sub.add_parser('regression').set_defaults(func=_cmd_regression)
    sub.add_parser('report').set_defaults(func=_cmd_report)

    p_eval = sub.add_parser('eval')
    p_eval.add_argument('--prompt-version', default=None, help='label for the candidate prompt version')
    p_eval.add_argument('--candidate-prompt-file', default=None, help='file with the candidate system prompt')
    p_eval.add_argument('--model', default=None, help='candidate model id (defaults to recorded/env model)')
    p_eval.set_defaults(func=_cmd_eval)

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == '__main__':
    sys.exit(main())
