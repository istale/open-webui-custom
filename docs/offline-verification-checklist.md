# Offline verification checklist (Stage 1 + Stage 2)

> **Purpose**: take this checklist to the offline machine that has real test
> data, run each section, and **fill in the right-hand column with the result**
> (a number, a verdict, or a short note — never raw user text). Bring this
> filled file back; that's all the info I need to plan Stage 3 prompt changes.
>
> **Data never has to leave the offline machine.** Every command outputs
> aggregates / skeletons / numbers. If something here would require copying raw
> user prompts, skip that step and note "skipped: PII".
>
> **Session-resilient**: this file is self-contained. If our chat drops, hand
> me back the filled checklist on a fresh session and I'll pick up from there.

---

## 0. Environment sanity (5 yes/no)

Run each, write `Y` / `N` / `note`:

| Check | Command | Result |
|---|---|---|
| Repo is at the right path | `cd /path/to/open-webui-based-project && git log -1 --oneline` | |
| Working venv usable | `<venv-python> -c "import aiohttp, pandas, aiocache; print('ok')"` | |
| Tests pass | `<venv-python> -m pytest tests/data_analysis/ -q \| tail -1` | |
| Ledger has data | `<venv-python> -c "import asyncio; from open_webui.models.data_analysis_events import DataAnalysisEvents; print(len(asyncio.run(DataAnalysisEvents.list_chat_ids())))"` (from `backend/`, with `PYTHONPATH=.`) | |
| `.env` has MINIMAX_* | `grep -c '^MINIMAX_' .env` (expect 3) | |

> All Stage-1 / Stage-2 commands below run from `backend/`, with:
> ```bash
> cd backend && set -a && . ../.env && set +a && export PYTHONPATH=.
> PY=<absolute path to venv python>
> CLI="$PY -m open_webui.utils.data_analysis.replay_cli"
> ```

---

## 1. Stage 1 — system health (already documented baselines)

Each command writes one JSON. Copy **only the numbers** into the right column.

### 1A. `report --since-days 30`
```
$CLI --since-days 30 report
```
Fill: `chats=___ turns=___ tool_calls=___ tool_failure_rate=___ self_correction_turns=___ chart_view_through_rate=___`
Top 3 failure codes (counts): `_______________________________`

### 1B. `regression --since-days 30`
```
$CLI --since-days 30 regression
```
Fill: `chats_replayed=___ replayable=___ matches=___ diverged=___ passed=___`
If diverged > 0 — names of diverged chat_ids (first 8 chars): `_______________`

### 1C. `eval --since-days 30` (live LLM — needs network)
```
$CLI --since-days 30 eval
```
Fill: `cases=___ errored=___ regressed_cases=___ passed=___`
If `cases=0`: note why (likely missing `prompt.submitted` or `model.request_prepared` pairing — see implementation-notes D17 + commit `3053f071a`).

---

## 2. Stage 2 — user-signal extraction (the new layer)

These three are the dimensions Stage 1 doesn't cover. Each output is an
aggregate; you can paste the whole JSON if it has no raw text, otherwise
fill the summary fields and a brief one-line interpretation.

### 2A. `intents --top 20 --since-days 30`
```
$CLI --since-days 30 intents --top 20
```
- `total_prompts = ___`
- `unique_skeletons = ___`
- **Skeleton diversity ratio** (unique / total): `___` — *low (<0.5) = users repeating patterns; high (>0.8) = wide question space*

**Top 5 skeletons (fill from output `top[0..4]`)**:

| # | skeleton (mask preserved, OK to keep verbatim — no PII) | count | dataset(s) | chart_types | success/failure | failure_codes |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |

**Sample column**: skeletons are safe to share. **Original prompt samples** under `sample` field — your call whether to bring back; if sensitive, replace with `[paraphrased: ___]`.

**Patterns to flag for me** (one-liners):
- Any skeleton with high count AND any failure: `____________`
- Any skeleton where multiple `chart_types` were used (indicates model inconsistency): `____________`
- Any skeleton with a `Line Sensor Readings`-style **display name** as a dataset value (= model didn't resolve dataset_id): `____________`

### 2B. `satisfaction --since-days 30`
```
$CLI --since-days 30 satisfaction
```
- `chats=___ turns=___ avg_turns_per_chat=___`
- `multi_turn_chat_rate=___` — *high (>0.4) = users refining = first answer often insufficient*
- `charts_rendered=___ charts_viewed=___ chart_view_through_rate=___` — *<0.5 = rendered but not looked at; the chart isn't being delivered well*
- `chats_with_render=___ chats_with_followup_click=___ followup_click_rate_when_rendered=___`

**Verdict (your sentence)**: `_______________________________________________`

### 2C. `fit --since-days 30`
```
$CLI --since-days 30 fit
```
- `turns_with_render_and_verb=___ matched=___ mismatched=___ fit_rate=___`
- `turns_no_intent_verb=___` — *high vs `turns_with_render_and_verb` means our verb map is too narrow; tell me which verbs to add*
- `turns_no_render=___`

**Sample mismatches (paste up to 5; skeletons are safe, original prompts at your discretion)**:

| # | verbs | expected_any_of | actual | sample_prompt (or paraphrase) |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

---

## 3. Open observations (subjective — fill what stands out)

> One short paragraph each. These are the things rules can't catch.

- **Where the model felt off**: `__________________________________________`
- **Where a chart would be better in a different form**: `__________________`
- **Domain vocabulary the model doesn't understand** (e.g. 良率, DPPM, Cp, Cpk, 偏移): `___________`
- **Anything in `report.failures_by_chart_type` that maps to a real workflow**: `___________`

---

## 4. What I'll do with this filled-in document

When you bring it back:

1. Section 2A → I'll **extend the system prompt** to handle the highest-count failing skeletons. Each maps directly to a prompt rule.
2. Section 2B → If view-through < 0.5 we'll **adjust how the model presents charts** (URL embedding, summary length, …).
3. Section 2C mismatches → I'll **expand `fit.py`'s `_VERB_TO_CHARTS` map** AND add corresponding system-prompt rules ("when user says 分布, prefer box/histogram unless time-axis").
4. Section 3 → drives **manual prompt rewrites** that pattern-matching can't suggest.
5. Each change goes through:
   - bump `DATA_ANALYSIS_PROMPT_VERSION` in `system-prompt.ts`
   - run `eval --candidate-prompt-file new.md` (offline `eval` is OK if MINIMAX_* reachable; else we'll mark as untested and just ship)
   - merge → next day's `daily-report.md` shows the effect

---

## 5. Quick reference (copy-paste ready)

```bash
# Stage 1 health
$CLI --since-days 30 report
$CLI --since-days 30 regression
$CLI --since-days 30 eval                 # needs network for MINIMAX

# Stage 2 user signals
$CLI --since-days 30 intents --top 20
$CLI --since-days 30 satisfaction
$CLI --since-days 30 fit
```

If any command fails: paste the **last 10 lines of the traceback** into Section 3
(no user data in tracebacks), and I'll know what to fix.
