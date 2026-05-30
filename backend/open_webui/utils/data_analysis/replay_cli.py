"""CLI to close the interaction-replay loop (Phase 4 / 5 / 6).

Run from the backend dir (the global `--since-days N` flag goes BEFORE the
subcommand):

    python -m open_webui.utils.data_analysis.replay_cli [--since-days N] <subcmd> [opts]

Subcommands:
- export     [--out trajectories.jsonl] [--redact]
             Write trajectory records (one JSON object per line) for downstream
             eval/training. Honours soft-delete + retention window + redaction.

- regression
             Replay every trajectory's recorded tool calls deterministically and
             diff vs. recorded outcomes. Exit code 1 if anything diverged (CI gate).

- report     Print aggregate analytics over trajectories: failure clustering by
             error_code / chart_type, self-correction (retry) rate, token totals,
             chart view-through rate, reward distribution.

- eval       [--prompt-version V] [--candidate-prompt-file F] [--model M] [--fewshot BANK.json]
             LLM-in-the-loop (Phase 5) — re-run each evaluable single-turn case's
             input against a candidate prompt / model / few-shot bank and score
             vs. the recorded baseline (rule-based checks). Exit code 1 if the
             candidate regresses any check (A/B gate). Needs a live endpoint:
             MINIMAX_BASE_URL / MINIMAX_API_KEY in env.

- mine       [--out fewshot_bank.json] [--prompt-version V] [--tool-spec-version V]
             [--per-cluster N] [--max N] [--redact]
             Few-shot mining (Phase 6) — select exemplary trajectories (reward /
             cleanliness gate, version-gate, diversity + dedup) and write a curated
             few-shot bank. Validate the bank by piping it back into `eval --fewshot`.
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

    system_suffix = None
    if args.fewshot:
        from open_webui.utils.data_analysis.fewshot import format_fewshot_block

        with open(args.fewshot, encoding='utf-8') as fh:
            system_suffix = format_fewshot_block(json.load(fh))

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
                system_suffix=system_suffix,
            )
            reports.append(score_candidate(_case_dict(case), _run_dict(run)))

    verdict = summarize_eval_reports(reports)
    verdict['prompt_version'] = args.prompt_version
    verdict['model'] = args.model
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0 if verdict['passed'] else 1


async def _cmd_mine(args) -> int:
    from open_webui.utils.data_analysis.fewshot import mine_fewshot
    from open_webui.utils.data_analysis.replay import export_trajectories

    trajs = await export_trajectories(since_ts=_since_ts(args.since_days), redact=args.redact)
    bank = mine_fewshot(
        trajs,
        current_prompt_version=args.prompt_version,
        current_tool_spec_version=args.tool_spec_version,
        per_cluster=args.per_cluster,
        max_examples=args.max,
        redact=args.redact,
    )
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(bank, fh, ensure_ascii=False, indent=2, default=str)
    print(f'mined {len(bank)} few-shot exemplars -> {args.out}')
    return 0


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
    p_eval.add_argument('--fewshot', default=None, help='few-shot bank JSON to inject (Phase 6 validation)')
    p_eval.set_defaults(func=_cmd_eval)

    p_mine = sub.add_parser('mine')
    p_mine.add_argument('--out', default='fewshot_bank.json')
    p_mine.add_argument('--prompt-version', default=None, help='version-gate to this prompt version')
    p_mine.add_argument('--tool-spec-version', default=None, help='version-gate to this tool spec version')
    p_mine.add_argument('--per-cluster', type=int, default=2, help='max exemplars per (chart_type, dataset)')
    p_mine.add_argument('--max', type=int, default=None, help='cap total exemplars')
    p_mine.add_argument('--redact', action='store_true')
    p_mine.set_defaults(func=_cmd_mine)

    args = parser.parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == '__main__':
    sys.exit(main())
