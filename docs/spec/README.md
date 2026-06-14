# Spec Docs — Dual Version System

> **目的**：每份 spec 維護兩個版本，給團隊不同情境用。
>
> **政策**：兩版必須在同一 commit 內同步更新。Teaching 是 source of truth。

---

## 為什麼有兩版

| 場景 | 你需要的版本 |
|---|---|
| 第一次讀，學 SvelteKit / FastAPI / Open WebUI 概念 | **Teaching**（`<name>.md`）|
| Onboarding 新成員 | Teaching |
| 開會討論「為什麼這樣設計」 | Teaching |
| 寫 code 時查 prop / event / schema 名 | **Brief**（`<name>.brief.md`）|
| Code review 對照規格 | Brief |
| Acceptance / DOD 檢查 | Brief |
| 看 anti-pattern 清單 | Brief |
| 跨團隊溝通決策（PM / 設計）| Brief |

---

## 對應表

| Teaching | Brief | 內容主題 |
|---|---|---|
| `PROJECT_GUIDE.md` | `PROJECT_GUIDE.brief.md` | Day 0 起手式、設計哲學 |
| `openwebui-module-inventory.md` | `openwebui-module-inventory.brief.md` | Tier 1/2/3 模組清單 |
| `tools-schema.md` | `tools-schema.brief.md` | Vertical features → tool calling |
| `database-adapter.md` | `database-adapter.brief.md` | Port/Adapter 對接外部資料系統 |
| `data-analysis-vertical-spec.md` | `data-analysis-vertical-spec.brief.md` | Manufacturing UX + chart types |
| `frontend-spec.md` | `frontend-spec.brief.md` | Frontend 契約（layout/stores/events/auto-scroll/native chat 整合） |
| `frontend-design-tokens.md` | `frontend-design-tokens.brief.md` | CSS 變數 / 字體 / 互動 pattern |
| `event-ledger.md` | `event-ledger.brief.md` | 行為觀測層、analytics events 表、emit 機制 |
| `inventory-results.md` | (不適用，是 worksheet) | Day 1 實測結果填寫表 |

---

## 版本差異原則

### Teaching 版包含
- ✅ 概念解釋（"什麼是 nested layout"）
- ✅ Why（"為什麼用 metadata 而不是新表"）
- ✅ 圖（layout、event flow、navigation map）
- ✅ Walkthrough（"使用者按下後發生什麼"）
- ✅ Step-by-step 實作指引
- ✅ Code 完整範例
- ✅ Anti-pattern + 為什麼錯
- ✅ Discussion / 比較不同方案

### Brief 版包含
- ✅ 決策結論（"用 Plan A"，不解釋三個 plan）
- ✅ Schema 定義（type / props / events）
- ✅ 檔案清單與職責
- ✅ Anti-pattern 列表（單行，不解釋）
- ✅ Acceptance checklist
- ❌ 概念解釋（→ link teaching）
- ❌ Walkthrough
- ❌ 多方案比較

### 連結規則
Brief 版內每個重要決策後加：「參考 [`<file>.md` §X.Y](./...md#anchor)」
Teaching 版頂部加：「⚡ Quick reference: [`<file>.brief.md`](./<file>.brief.md)」

---

## 維護流程

### 改動時
1. **先改 teaching 版**（含 why / discussion）
2. **distill 到 brief 版**（只更新決策、schema、清單）
3. **同 commit 提交兩份**
4. Commit 訊息開頭：`spec: ...` (兩版都要在 message 提及)

### Drift 偵測
之後加 pre-commit hook：
```bash
# .git/hooks/pre-commit
for f in docs/spec/*.md; do
    if [[ ! "$f" =~ \.brief\.md$ && "$f" != "README.md" ]]; then
        brief="${f%.md}.brief.md"
        if [ -f "$brief" ]; then
            # check both staged together
            if git diff --cached --name-only | grep -q "$f" && \
               ! git diff --cached --name-only | grep -q "$brief"; then
                echo "ERROR: $f changed but $brief not staged"
                exit 1
            fi
        fi
    fi
done
```

---

## 給團隊的閱讀順序建議

### 第一週（Onboarding）
1. `PROJECT_GUIDE.md`（teaching）— 整體哲學
2. `openwebui-module-inventory.md`（teaching）— 學會什麼可重用
3. `frontend-spec.md` §1（teaching）— SvelteKit + 路由 + native chat 概念
4. `tools-schema.md`（teaching）— Tool calling 機制
5. `database-adapter.md`（teaching）— Port/Adapter 模式

### 第二週起（實作）
1. 主要看 brief 版查 schema / props / events
2. 不確定 why 才回 teaching 版
3. 改動 spec 時兩版一起改

---

## 給 Code Agent 的指引

寫 code / PR description 時：
- 引用規格用 brief 版（精確）
- 解釋 why 時引用 teaching 版（完整）
- 例：「依 `frontend-spec.brief.md` §3 store shape...; 詳見 `frontend-spec.md` §3.2 為什麼 derived 而非 store」

修改 spec 時：
- 兩版必須同 commit 改
- Brief 不可超過 teaching 30% 篇幅
- Teaching 不可省略 brief 有的內容
