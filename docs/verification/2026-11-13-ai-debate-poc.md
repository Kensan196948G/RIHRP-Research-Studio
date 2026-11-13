# AI 討論 PoC 実装・検証（2026-11-13）

- 対象: Phase 3 B PoC（03 討論のみ・assist・既定 OFF）
- 関連: [ADR-0007](../adr/0007-studio-ai-debate.md) / [設計](../design/03-studio-llm-replacement-plan.md) / [テスト計画](../testing/06-ai-debate-test-plan.md)

## 目的

スタジオの討論（03）に限り、サーバー側 LLM で発言候補を生成する。生成物は保存せず、
利用者がプレビューを確認して採用したときだけ研究文書に保存する。検証・スコア・採点・採択の
決定論（ADR-0002）は変更しない。

## 実装

- API: `POST /api/projects/{id}/ai/debate`（editor 以上、body なし）。
- LLM: `llm.generate_debate`（promptVersion `studio-debate-v1`）。仮説・資料 8 件・批判 6 件に限定。
  evidence ID 実在チェックに失敗した発言は破棄。
- UI: 03 の「✦ AIで討論を生成（試行）」→ プレビュー →「採用」/「破棄」。
  採用時だけ `debate[]`（`evidenceIds` 付き）と `debateAi`（provider/model/promptVersion/generatedAt）を保存。
- 監査: `ai.debate_requested`（provider/model/promptVersion/件数/latency）。本文・鍵は残さない。
- 既定 OFF: `RIHRP_LLM_*` 未設定なら 503 `ai_not_configured`。キー未投入では外部通信なし。

## 検証結果

| 範囲 | 結果 |
|---|---|
| API（スタブ）`test_ai_debate.py` | **11 passed**（成功・403・503・422・未知 ID・混在 ID・401・不正 JSON・timeout・429・監査） |
| 既存 AI 下書き（回帰）`test_ai_drafting.py` | **11 passed** |
| ブラウザ E2E `ai-debate.spec.ts` | **1 passed（4.0s）**（プレビュー→採用→保存、採用前は不変） |
| 全 E2E（スタブ） | **44 passed / 1 skipped / 0 failed（2.2 分）** |
| Web build / vitest | build OK / **10 passed** |

## セキュリティ・監査

- 生成物は保存せず、採用時のみ保存する（幻覚の固定化を避ける）。
- 引用は既存 evidence ID のみ。未知 ID の発言は破棄（テスト D-05/D-06）。
- 鍵・プロンプト・生成本文は応答・監査に含めない（D-07/D-11）。
- 既存の timeout / レート制限 / fail-closed を流用（D-03/D-09/D-10）。

## 残リスク・未検証

- 実キーでのスモークは未実施（人間の承認が必要）。
- evidence ID の実在チェックは**主張の支持関係**を保証しない。実在 ID で内容が異なる場合、
  数値・単位の不一致、引用なしの断定は人間レビューに残る（LHT-02/03/06）。
- 資料内プロンプトインジェクションへの耐性、根拠不足時の棄権は実キーで未検証（LHT-04/05、P0/P1）。
- 品質ルーブリックの評定者・閾値は未確定。

## Skill 適用記録

| Skill | 時点 | 状態 |
|---|---|---|
| `ai-feature-testing` | 設計前 | 適用済み |
| `llm-hallucination-testing` | テスト設計 | 適用済み（LHT-01〜06、D-13〜D-16） |
| `ai-generated-test-review` | 実装後 | 未適用（テストは本セッションで人手設計。次回適用） |
| `test-report-review` | 記録時 | 未適用（承認前に適用） |

## 変更ファイル

- `apps/api/rihrp/llm.py` / `apps/api/rihrp/routers/ai.py`
- `apps/web/src/studio/api.ts` / `apps/web/src/studio/engine.js`
- `tests/integration/test_ai_debate.py` / `tests/e2e/llm_stub.py` / `apps/web/e2e/ai-debate.spec.ts`
- `docs/adr/0007-studio-ai-debate.md` / `docs/design/03-studio-llm-replacement-plan.md`
- `docs/testing/05-automation-3layers.md` / `docs/testing/06-ai-debate-test-plan.md`
- `CHANGELOG.md`
