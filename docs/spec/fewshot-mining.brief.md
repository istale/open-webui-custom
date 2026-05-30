# Few-shot Mining — Brief / Contract Version (Phase 6)

> **Quick reference of `fewshot-mining.md`. 修改本檔時必須同步更新 teaching 版。**

Select exemplary trajectories → distill to a curated few-shot bank
(`request → ideal tool sequence → answer`). Built on
[`interaction-replay.brief.md`](./interaction-replay.brief.md); validated by
[`llm-eval.brief.md`](./llm-eval.brief.md).

---

## Scope (v1)
- **Offline artifact only.** Mine to versioned `fewshot_bank.json`; do **not** wire
  into the live prompt yet. Live injection into `buildDataAnalysisSystemPrompt` is a
  reviewed follow-up.

---

## Selection pipeline (`fewshot.py`, pure)
Candidate kept only if, in order:
1. **Reward/clean** — thumbs-up OR zero tool failures (one recover-and-retry ok; thrashing out).
2. **Still works** — `replay_trajectory(...).passed == True` (Phase 2 reuse).
3. **Version-gate** — `prompt_version`/`tool_spec_version` == current (D16).
4. **Diversity** — cluster by `(intent, chart_type, dataset)`, keep best 1–2/cluster, token-capped.

---

## Exemplar format
```
{ user_request, tool_sequence:[{tool,args}...], final_answer,
  provenance:{chat_id,message_id,prompt_version,tool_spec_version,reward} }
```
Free-text redactable; tool-arg structure is the signal. Deduped by content hash.

---

## Closing the loop
- **Phase 6 produces candidates; Phase 5 eval is their acceptance test.**
- Keep an exemplar only if it improves (or doesn't regress) the rule-based eval score
  with-vs-without injection. Unfalsifiable without Phase 5 → 5 ships first.

---

## CLI
```
replay_cli [--since-days N] mine --out fewshot_bank.json \
  [--prompt-version V] [--tool-spec-version V] [--per-cluster N] [--max N] [--redact]
replay_cli --since-days N eval --fewshot fewshot_bank.json      # the gate
```

---

## Governance
- **Consent** — `mine` uses `export_trajectories` → `is_deleted` chats excluded; deleted ⇒ never an exemplar.
- **Anonymization** — `--redact` masks free-text, keeps tool-arg structure.
- **Provenance** — every exemplar records chat_id/message_id/versions → auditable, re-mineable on version bump.

---

## Anti-patterns
- ❌ Inject mined bank into live prompt before review → offline artifact first.
- ❌ Mine across prompt/tool versions → version-gate to current.
- ❌ Keep exemplars that don't improve eval score → gate via Phase 5.
- ❌ Mine deleted/soft-deleted chats → `export_trajectories` excludes them.

---

## 跨檔關聯
- Replay 基礎：[`interaction-replay.brief.md`](./interaction-replay.brief.md)
- 驗收工具：[`llm-eval.brief.md`](./llm-eval.brief.md)
- 決策日誌：[`../implementation-notes.md`](../implementation-notes.md)
