"""CLI to close the interaction-replay loop (Phase 4).

Run from the backend dir:

    python -m open_webui.utils.data_analysis.replay_cli export    --out traj.jsonl [--since-days N] [--redact]
    python -m open_webui.utils.data_analysis.replay_cli regression [--since-days N]
    python -m open_webui.utils.data_analysis.replay_cli report     [--since-days N]

- export:     write trajectory records (one JSON object per line) for eval/training.
- regression: replay every trajectory's recorded tool calls deterministically and
              diff vs. recorded outcomes; exit code 1 if anything diverged (CI gate).
- report:     print aggregate analytics (failure clustering, retry rate, etc.).
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

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == '__main__':
    sys.exit(main())
