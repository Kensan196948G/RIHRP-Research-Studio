# AI 批判・候補提案 PoC 実装・検証（2026-11-13）

- 対象: Phase 3 C PoC（04 根拠・反証の批判提案 / 05 新仮説比較の候補提案・生成のみ・既定 OFF）
- 関連: [ADR-0008](../adr/0008-studio-ai-critiques-candidates.md) / [設計 04](../design/04-studio-ai-critiques-candidates.md) / [テスト計画 08](../testing/08-ai-critique-candidate-test-plan.md) / [ADR-0007](../adr/0007-studio-ai-debate.md)

## 目的

04/05 に AI の文面提案を追加する。生成物は保存せず、利用者がプレビューを確認して採用したときだけ
研究文書に追加する。**AI は採点しない**。採用後は既存の `scoreCand()` が決定論で採点する。

## 実装

- API: `POST /api/projects/{id}/ai/critiques` / `POST /api/projects/{id}/ai/candidates`（editor 以上・body なし・保存しない）。
- LLM: `llm.generate_critiques` / `llm.generate_candidates`（promptVersion `studio-critique-v1` / `studio-candidates-v1`）。
  - 批判: 最大 6 件。`cat`/`text`/`sug` のみ。**sev/status は返さない**。存在しない evidence ID の item は破棄。
  - 候補: 最大 5 件。`type` は既存 enum、`vars` は分析済み変数のみ、**scores/total/status は破棄**。
  - 入力は研究文書の限定フィールド（仮説・分析・資料 8・批判 6・候補 5）に切り詰め、DATA として隔離。
- UI: 04/05 に「✦ AIで批判/候補を提案（試行）」→ プレビュー →「採用」/「破棄」。
  採用時のみ `critiques[]`（sev 低・未対応・origin AI提案）/ `candidates[]`（候補・origin AI提案）を追加し、
  候補は `scoreAll()` で再採点。`aiAssist.critiques` / `aiAssist.candidates` に provenance を保存。
- 監査: `ai.critique_requested` / `ai.candidate_requested`（provider/model/prompt_version/件数/latency）。本文・鍵は残さない。
- 既定 OFF: `RIHRP_LLM_*` 未設定は 503。レート制限は討論と共通。

## 検証結果

| 範囲 | 結果 |
|---|---|
| API（スタブ）`test_ai_critique_candidate.py` | **13 passed**（成功・不正 ID 破棄・全滅 502・不正出力・共有レート・監査・採点破棄・未知 type/vars・上限・422・401・403・503） |
| 既存 AI 討論（回帰）`test_ai_debate.py` | **13 passed** |
| 既存 AI 下書き（回帰）`test_ai_drafting.py` | **11 passed** |
| 全 pytest | **434 passed / 1 skipped / 0 failed** |
| ブラウザ E2E `ai-assist.spec.ts` | **2 passed**（A-01 2.4s / A-02 2.4s。破棄で不変、採用時のみ保存、候補は既存ロジックで採点） |
| 全 E2E（スタブ） | **46 passed / 1 skipped / 0 failed（2.2 分）** |
| Web build / vitest | build OK / 10 passed |

証跡: [API テストログ](2026-11-13-ai-critique-candidate/api-tests.txt)（SHA-256 `028a61a2…`）/
[全 E2E ログ](2026-11-13-ai-critique-candidate/e2e-full.txt)（`ba663a0c…`）。

## セキュリティ・監査

- 生成物は保存せず、採用時のみ追加する（幻覚の固定化を避ける）。
- 引用は既存 evidence ID のみ。未知 ID の item は破棄（全滅なら 502）。
- AI の採点値はサーバーで破棄。スコアは採用後に既存の決定論ロジックで算出する。
- 鍵・プロンプト・生成本文は応答・監査に含めない。
- timeout / レート制限 / fail-closed は既存基盤を流用（討論と共通バケット）。

## 決定論の確認

- API 応答に `scores` / `total` / `status` が含まれないこと（C-07）。
- E2E で、採用後に `scores.evidence` と `total` が数値で付与されること（A-02）。
- 採点は `scoreCand()` のみ。AI の有無でスコア計算式は変化しない。

## 残リスク・未検証

- 実キーでの品質・幻覚率・注入耐性・棄権は未検証（LHT-C4/C5/C6）。**有効化前のゲート**。
- AI が提案した文面の意味的な妥当性は人間レビュー。スコアは文面から決定論的に計算されるが、
  文面そのものの正しさは保証しない。
- 討論 E2E と同様、手動 E2E ワークフローにはスタブ未配線のため CI では skip される（条件 C3）。
- 評定者 2 名・閾値（Q6 相当）は未確定。

## Skill 適用記録

| Skill | 時点 | 状態 |
|---|---|---|
| `ai-feature-testing` | 設計前 | 適用済み（設計 §5 のリスク・失敗系） |
| `llm-hallucination-testing` | テスト設計 | 適用済み（LHT-C1〜C6、テスト計画 08 §2） |
| `ai-generated-test-review` | 実装後 | 適用済み（弱い assertion 1 件を修正し、不正出力・共有レート・上限の 3 件を追加） |
| `test-report-review` | 記録作成時 | 適用済み（[レビュー記録](2026-11-13-test-report-review-ai-assist.md)、`conditional_pass`） |

## 実行主体（AI・Agent・Skill）

- モデル / 提供元: DSH の `deepseek-flash`（DeepSeek）。テスト生成はローカルスタブで実行し、実 LLM は呼び出していない。
- Agent: Lead 1 名。サブエージェントは未使用。
- Skill: 上表のとおり。必須 Skill の未適用はなし。
- 注意: 本記録は「スタブ検証」と「既定 OFF の不変性」の記録であり、実 LLM の品質・安全性の証明ではない。

## 変更ファイル

- `apps/api/rihrp/llm.py` / `apps/api/rihrp/routers/ai.py`
- `apps/web/src/studio/api.ts` / `apps/web/src/studio/engine.js`
- `tests/integration/test_ai_critique_candidate.py` / `tests/e2e/llm_stub.py` / `apps/web/e2e/ai-assist.spec.ts`
- `docs/adr/0008-studio-ai-critiques-candidates.md` / `docs/design/04-studio-ai-critiques-candidates.md`
- `docs/testing/08-ai-critique-candidate-test-plan.md` / `docs/verification/2026-11-13-ai-critique-candidate.md`
- `docs/api/openapi.yaml` / `CHANGELOG.md`
