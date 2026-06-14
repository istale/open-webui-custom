# LLM-in-the-loop Eval — Teaching Version (Phase 5)

> **修改本檔時必須同步更新 [`llm-eval.brief.md`](./llm-eval.brief.md)。**
> Builds on [`interaction-replay.md`](./interaction-replay.md). Decision log in
> [`../implementation-notes.md`](../implementation-notes.md).

## 1. Why this exists

Phases 0–4 let us *replay the recorded tool calls* of a past trajectory and check
they still work (a deterministic regression signal). That answers "did our tools
break?" — but **not** "would a *different prompt or model* have handled this turn
better?". Improving an agent means being able to test a candidate change against
real, already-seen inputs *before* shipping it. That is LLM-in-the-loop eval:
re-run the captured **input** against a **candidate** (different prompt version,
model, or params), then score the candidate's behaviour against the recorded
baseline.

Replay re-runs the tools and freezes the LLM; eval re-runs the LLM and (still)
runs its tool calls deterministically. They are complementary.

## 2. Scope (v1): single-turn

A captured turn's input is reconstructed from two ledger signals:
- `model.request_prepared` → `system_prompt` (full, incl. ephemeral
  `[Workspace context]`), `model`, curated `params`, `tool_ids`.
- `prompt.submitted` → the user's text.

The snapshot stores `message_count` but **not** the full prior message list, so
multi-turn history can't be faithfully reconstructed. v1 therefore evaluates
**single-turn** cases only and marks turns with `message_count > 2`
(system + user) as **`not_evaluable`** — the same version/schema-gating discipline
that keeps replay honest (interaction-replay §7 / D16). No snapshot change is made;
multi-turn is revisited only if the data shows it's common.

## 3. How a case is evaluated

```
eval_case = build_eval_case(trajectory)        # input + recorded outcome + reward
candidate = run_candidate(eval_case,           # ONE live LLM call
              candidate_prompt=?, candidate_model=?, params=?)
report    = score_candidate(eval_case, candidate)
```

1. **`build_eval_case`** — pulls `system_prompt`, `user_prompt`, `tool_ids`, and the
   recorded outcome (tool sequence, success/failure, reward) from the trajectory.
2. **`run_candidate`** — issues a single completion via the provider client (§4),
   substituting the candidate prompt/model/params. The candidate's returned tool
   calls are then **fed through the existing `replay_trajectory` machinery** against
   the deterministic `InMemoryDatasetRepository`, so tool success/failure is
   reproducible and not merely self-reported by the model.
3. **`score_candidate`** — rule-based scoring (§5).

The only non-deterministic step is the single LLM call; everything downstream of it
is deterministic, so two eval runs differ only by model sampling.

## 4. Provider client (the one live-LLM seam)

`llm_client.py` is a thin async wrapper over the OpenAI-compatible endpoint already
configured in `.env` (`MINIMAX_BASE_URL`, `MINIMAX_API_KEY`, `MINIMAX_MODEL`). One
method:

```
async def complete(*, system: str, messages: list, tools: list, params: dict)
    -> list[output_item]      # OR-style function_call / message items
```

It is the **only** module in the data-analysis vertical that performs live LLM I/O.
Keeping the seam isolated means replay/analytics/trajectory stay pure and offline,
and eval is the single place that needs network + a key.

## 5. Scoring (v1): rule-based, deterministic

Each check maps 1:1 to a system-prompt rule, so a failing candidate names the exact
rule it broke. These are the same failure modes seen in live QA.

| Check | Pass condition |
|---|---|
| `used_tools` | Called `query_dataset` (didn't freelance pandas/matplotlib) |
| `resolved_dataset` | Used a real `dataset_id` (didn't guess from display name → DATASETNOTFOUND) |
| `render_succeeded` | `render_chart` returned success when a chart was warranted |
| `recovered_query_id` | On expired/`not found` query_id, re-queried then retried (rule 5) |
| `embedded_real_url` | Inlined the exact returned chart url, not a placeholder |
| `tool_workflow_ok` | query → render ordering respected |

Aggregate verdict compares candidate vs baseline per check:
**improved / unchanged / regressed**. LLM-as-judge (narrative quality 1–5) is
explicitly **out of v1 scope** — added later behind a `--judge` flag; documented as
a follow-up so token cost and non-determinism are opt-in.

## 6. CLI

```
python -m open_webui.utils.data_analysis.replay_cli --since-days 30 eval \
    [--prompt-version da-sys-XXXX]      # label for the candidate prompt version
    [--candidate-prompt-file FILE]      # actual candidate system prompt text
    [--model MiniMax-MX]                # candidate model id (defaults to recorded/env)
    [--fewshot fewshot_bank.json]       # Phase 6 validation: inject a mined bank
```

(`--since-days` is the global retention window — it goes BEFORE the subcommand.
Redaction is an export/mine flag; `eval` doesn't persist text, only scores.)

Prints per-case baseline-vs-candidate diffs and an aggregate verdict (mirrors
`summarize_replay_reports`). **Exits non-zero if the candidate regresses on any
rule-based check** → drop-in A/B gate for prompt/model changes.

## 7. Governance

Eval reads the sensitive raw `system_prompt` / `prompt_text` and calls the user's
own endpoint. It introduces **no new persistence** of user data — outputs are scores
plus candidate text held in CLI output, masked when `--redact` is set. Same
soft-delete / retention rules as export (a deleted chat's trajectory is excluded).

## 8. What's next
LLM-as-judge scoring (flagged), multi-turn support (needs a snapshot message digest),
and using eval as the acceptance test for mined few-shots
([`fewshot-mining.md`](./fewshot-mining.md) §closing-the-loop).
