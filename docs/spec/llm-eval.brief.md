# LLM-in-the-loop Eval — Brief / Contract Version (Phase 5)

> **Quick reference of `llm-eval.md`. 修改本檔時必須同步更新 teaching 版。**

Re-run a captured turn's **input** against a **candidate** (prompt/model/params),
score the candidate's behaviour vs the recorded baseline. Complements replay
(which freezes the LLM and re-runs tools); eval re-runs the LLM, tools still
deterministic. Built on [`interaction-replay.brief.md`](./interaction-replay.brief.md).

---

## Scope (v1)
- **Single-turn only.** Input = `model.request_prepared.system_prompt` +
  `prompt.submitted` text + `tool_ids`.
- Snapshot stores `message_count`, not full history → turns with `message_count > 2`
  are **`not_evaluable`** (version/schema-gating, like replay D16). No snapshot change.
- **Rule-based scoring only.** LLM-judge is out of v1 (later, behind `--judge`).

---

## Flow
```
build_eval_case(trajectory) -> {system_prompt, user_prompt, tool_ids, recorded_outcome, reward}
run_candidate(case, candidate_prompt?, candidate_model?, params?) -> output_items   # 1 live LLM call
   -> candidate tool calls fed through replay_trajectory() (deterministic repo)
score_candidate(case, candidate) -> report
```
Only the single LLM call is non-deterministic; everything after is deterministic.

---

## Modules (`backend/open_webui/utils/data_analysis/`)
- `llm_client.py` — async `complete(system, messages, tools, params) -> output_items`.
  **Only** vertical module doing live LLM I/O. Uses `.env` MINIMAX_* config.
- `eval.py` — `build_eval_case`, `run_candidate`.
- `scoring.py` — rule-based `score_candidate` (table below), aggregate verdict.
- `replay_cli.py eval` — CLI; **non-zero exit on regression** → A/B gate.

```
python -m open_webui.utils.data_analysis.replay_cli eval \
  --prompt-version da-sys-XXXX --model Y [--since-days N] [--redact]
```

---

## Rule-based checks (each maps to a system-prompt rule)
| Check | Pass |
|---|---|
| `used_tools` | called query_dataset, no freelance code |
| `resolved_dataset` | real dataset_id (no display-name guess) |
| `render_succeeded` | render_chart ok when chart warranted |
| `recovered_query_id` | re-query+retry on expired id (rule 5) |
| `embedded_real_url` | exact returned chart url, no placeholder |
| `tool_workflow_ok` | query→render ordering |

Verdict per check: improved / unchanged / regressed.

---

## Governance
- Reads raw `system_prompt`/`prompt_text`; calls user's own endpoint.
- **No new persistence** — scores + candidate text only; `--redact` masks free-text.
- Honours soft-delete / retention via the trajectory source (deleted chats excluded).

---

## Anti-patterns
- ❌ Trust the model's self-reported tool success → re-run tools via `replay_trajectory`.
- ❌ Evaluate multi-turn from `message_count` alone → mark `not_evaluable`.
- ❌ Add LLM I/O to trajectory/replay/analytics → keep it in `llm_client.py` only.
- ❌ Ship LLM-judge in v1 → flagged follow-up.

---

## 跨檔關聯
- Replay 基礎：[`interaction-replay.brief.md`](./interaction-replay.brief.md)
- 下游消費：[`fewshot-mining.brief.md`](./fewshot-mining.brief.md)
- 決策日誌：[`../implementation-notes.md`](../implementation-notes.md)
