# Few-shot Mining from High-reward Trajectories — Teaching Version (Phase 6)

> **修改本檔時必須同步更新 [`fewshot-mining.brief.md`](./fewshot-mining.brief.md)。**
> Builds on [`interaction-replay.md`](./interaction-replay.md) and is validated by
> [`llm-eval.md`](./llm-eval.md). Decision log in
> [`../implementation-notes.md`](../implementation-notes.md).

## 1. Why this exists

Once you can capture trajectories and tell good ones from bad ones (reward + replay
+ eval), the highest-leverage use is **teaching the model from its own best runs**.
Few-shot mining selects exemplary trajectories and distills them into a curated bank
of `request → ideal tool sequence → answer` examples that can prime the model toward
the tool workflow it already nailed before.

## 2. Scope (v1): offline artifact

The bank is produced and validated **offline** — written to a versioned
`fewshot_bank.json`, *not* wired into the live prompt yet. This lets you inspect and
curate exemplars before they change model behaviour. Live injection into
`buildDataAnalysisSystemPrompt`'s `[Workspace context]` builder is a deliberate,
separate follow-up once the bank is trusted.

## 3. Selection pipeline (`fewshot.py`, pure + testable)

A trajectory becomes a candidate exemplar only if it passes, in order:

1. **Reward & cleanliness** — thumbs-up (from the feedback overlay, `attach_feedback`),
   OR no rating but zero tool failures. A single recover-and-retry (expired query_id →
   re-query → success) is acceptable; repeated thrashing disqualifies.
2. **Still works** — `replay_trajectory(...).passed` is `True` (the recorded tool
   sequence reproduces today; reuses Phase 2 replay). Stale exemplars that no longer
   run are dropped.
3. **Version-gate** — `prompt_version` / `tool_spec_version` match *current* (D16
   discipline). Exemplars from an old prompt teach old behaviour.
4. **Diversity / dedup** — cluster by `(intent, chart_type, dataset)` and keep the
   best 1–2 per cluster, capped to a token budget. Prevents a bank of 20 near-identical
   line charts; favours coverage of the input space.

## 4. Exemplar format

Each kept trajectory is distilled to a compact, structural example:

```
{
  "user_request":  "<prompt.submitted text>",
  "tool_sequence": [
     {"tool": "query_dataset", "args": {"dataset_id": "...", "sql": "..."}},
     {"tool": "render_chart",  "args": {"chart_type": "...", "x": "...", "y": "...", "color": null}}
  ],
  "final_answer":  "<assistant message>",
  "provenance":    {"chat_id", "message_id", "prompt_version", "tool_spec_version", "reward"}
}
```

Free-text (`user_request`, `final_answer`) is redactable; the structure + tool args
are the teaching signal. Deduped by content hash so reloads/re-mines don't double-count.

## 5. Closing the loop (the important part)

A mined exemplar is only kept if it **measurably helps**. The bank is validated
through Phase 5 eval: run `eval` over a held-out set of cases **with** and **without**
the bank injected, and keep only exemplars whose presence improves the rule-based
score (or at least doesn't regress it). So:

- **Phase 6 produces candidates; Phase 5 is their acceptance test.**
- An exemplar that doesn't move the needle — or regresses it — is dropped.

This is why Phase 5 is sequenced first: without it, few-shot mining is unfalsifiable.

## 6. CLI

```
# 1. mine the bank
python -m open_webui.utils.data_analysis.replay_cli mine \
    --out fewshot_bank.json [--max N] [--min-reward ...] [--redact]

# 2. validate it improves scores (Phase 5)
python -m open_webui.utils.data_analysis.replay_cli eval \
    --fewshot fewshot_bank.json --since-days 30
```

`mine` is pure selection + formatting; the eval step is the gate that decides whether
the bank ships.

## 7. Governance

- **Consent / soft-delete** — `mine` draws from `export_trajectories`, which already
  excludes `is_deleted` chats, so a deleted chat can never become a few-shot.
- **Anonymization** — `--redact` masks the free-text fields while keeping tool-arg
  structure; redact before sharing a bank externally.
- **Provenance** — every exemplar records its `chat_id` / `message_id` / versions, so a
  bank is auditable back to its source turns and re-mineable when versions bump.

## 8. What's next
Live injection into the system-prompt builder (behind review), reward-weighted
selection once more thumbs data accrues, and clustering-driven gap analysis ("which
intents have no good exemplar yet").
