# AI 生成テストのレビュー（2026-11-13・AI 討論 PoC）

- 適用 Skill: `ai-generated-test-review`（実装後の**事後適用**）
- 対象: PR #50（`feat/ai-debate-poc`）の AI 討論テスト
- 対象ファイル: `tests/integration/test_ai_debate.py`（11 tests）/ `apps/web/e2e/ai-debate.spec.ts`（1 test）
- 契約の根拠: `apps/api/rihrp/routers/ai.py`（debate endpoint）、`apps/api/rihrp/llm.py`（`_debate_messages` / `generate_debate`）
- review_type: AI-assisted recommendation / human_final_decision: pending

## 1. Review Conclusion

- 範囲: 討論 API の結合テスト 11 件と、討論 E2E 1 件。既存 AI 下書きテストは回帰確認のみ（本レビューの対象外）。
- 証跡: 実装コード、テストコード、ローカル実行（`11 passed` / E2E `1 passed 4.0s`、全 E2E `44 passed / 1 skipped`）、CI run `43344307954`（3 ジョブ success）。
- 総合 confidence: medium。同一 Agent が実装とレビューを行っており独立性は限定的。実キーでの挙動は本レビューの範囲外（未供給）。
- 未解決の問い: 実キーでの引用支持関係・注入耐性は未評価（テスト計画 LHT-01〜06 の範囲）。E2E は標準ワークフローで自動実行されない（§4）。

## 2. P0 / P1 Findings

| 重要度 | 箇所 | 問題 | 誤って緑になる筋 | 対応 |
|---|---|---|---|---|
| **P1（修正済み）** | `test_ai_debate.py:231` mixed | 混在応答で `len(messages) == 3` しか見ておらず、**どの発言を落としたか**を検証していなかった | 不正 ID の発言ではなく**有効な発言を 1 件落とす**実装でも件数 3 で通る | 残存メッセージの本文一致と `"missing"` 非混入を追加（修正済み） |
| **P1（修正済み）** | `test_ai_debate.py:287` audit | 監査に action と「秘密・本文なし」だけを要求し、記録される **provider/model/prompt_version/件数/latency** を検証していなかった | 監査メタデータを落とす退行（追跡不能化）でも通る | `details` の各項目を追加検証。あわせて `project_id` で監査を絞り決定化（修正済み） |
| **P1（未対応・非ブロッカー）** | `.github/workflows/e2e.yml` | 手動 E2E ワークフローに LLM スタブの起動・`RIHRP_E2E_LLM_BASE_URL` 設定がなく、討論 E2E は**CI 経由では skip** される | ローカル手順（スタブ手動起動）を知らないと「E2E で担保済み」と誤認する | スタブ起動＋env 設定を追加し `workflow_dispatch` で PASS を確認する（§5/§6） |

## 3. Per-Test Verdict

API（`tests/integration/test_ai_debate.py`）:

| Test | 判定 | 意図 | 実際の assertion | 最小のすり抜けバグ |
|---|---|---|---|---|
| `returns_messages_without_saving` (176) | STRONG | 生成のみ・保存しない | 200 / 件数 / evidenceIds / model / prompt_version / 鍵非漏洩 / version・payload 不変 | 生成時に保存する（version 不変で検出） |
| `is_editor_only` (196) | STRONG | viewer 拒否 | 403 | viewer を許可（403 で検出） |
| `without_key_fails_closed` (202) | STRONG | 未設定は fail-closed | 503 + `ai_not_configured` | キー空でも外部呼び出し（503 で検出。呼び出し有無は未検証） |
| `without_hypothesis_is_rejected` (214) | STRONG | 入力検証 | 422 + `validation_error` | 仮説空で生成実行（422 で検出） |
| `unknown_evidence_ids_are_rejected` (223) | STRONG | 全滅なら 502 | 502 + `ai_invalid_output` | 未知 ID を素通し（502 で検出） |
| `mixed_evidence_ids...` (231) | STRONG（修正後） | 不正 ID の発言だけ落とす | 200 / 件数 / **本文一致** / `"missing"` 非混入 | 有効発言を落とす・並び替える（本文一致で検出） |
| `upstream_401_becomes_502...` (245) | STRONG | 上流 401 を 502 に変換し鍵を出さない | 502 + `ai_upstream_error` / 鍵非漏洩 / スタブが Bearer を受領 | 鍵を応答へ漏らす・上流 401 を 401 で返す |
| `invalid_output_becomes_502` (257) | STRONG | 不正 JSON | 502 + `ai_invalid_output` | 不正 JSON を素通し |
| `timeout_becomes_504` (265) | STRONG | タイムアウト変換 | 504 + `ai_timeout` | タイムアウトを 500 で返す |
| `rate_limit_is_enforced` (273) | STRONG | 回数制限 | 1 回目 200 / 2 回目 429 | 制限なし（429 で検出。error code は未検証） |
| `is_audited_without_prompt_or_key` (287) | STRONG（修正後） | 監査に本文・鍵を残さない | action 存在 / 鍵・プロンプト・生成本文なし / **メタデータ各項目** | メタデータ欠落退行（追加 assertion で検出） |

E2E（`apps/web/e2e/ai-debate.spec.ts:36`）: **STRONG**（対象経路）。プレビュー中は `version` 不変・`debateAi` 未定義、採用後に `debateAi` と 3 件が保存されることを `expect.poll` で確認。すり抜け: 破棄時に保存する退行（破棄経路のテストなし）、`evidenceIds` の保存欠落（未 assertion）。

## 4. Coverage Gaps and Residual Risks

- **未実行（実キー必要・計画で out_of_scope）**: LHT-02（根拠支持整合）/ LHT-03（引用なし断定）/ LHT-04（棄権）/ LHT-05（注入・P0）/ LHT-06（数値・単位）。
- **未テストの境界**: `_debate_messages` のスキーマ検査（不正 agent・空 kind・短すぎる text の破棄）は実装にあるが直接テストがない。
- **未テストの経路**: 未認証 401（討論 API 自体）、レート制限の error code、E2E の破棄経路、E2E の `evidenceIds` 保存。
- **実行環境の差**: 討論 E2E は手動 E2E ワークフローでは skip（§2 P1）。CI で常時実行されるのは API テストのみ。
- **独立性**: 実装・テスト・レビューが同一 Agent。レビューは「緑の理由」を要求する形に留まり、独立した第 3 者評価ではない。

## 5. P2 Improvements

1. `test_mixed...` に続き、スキーマ破棄（不正 agent / 短 text）のケースを追加する。
2. `test_rate_limit_is_enforced` で `error.code == "rate_limited"` を検証する。
3. 討論 API の未認証 401 を明示テストする（PR 本文の「401」は上流 401 のみで、利用者認証の 401 ではない）。
4. E2E に破棄経路と `evidenceIds` 保存の assertion を追加する。
5. e2e.yml にスタブ起動と env 設定を追加し、討論 E2E を CI 実行可能にする。

## 6. Recommended Verification Order

1. API 単体（`pytest tests/integration/test_ai_debate.py`）→ 2. 全 pytest（回帰）→ 3. Web vitest / build → 4. E2E（スタブ起動。討論 spec 単体 → 全 E2E）→ 5. 実キー評価（人間の承認後・有効化前）。

## 付記

- 本レビューで修正した 2 件（P1）は同一 PR 内でコミット済み。テスト件数は 11 件のまま（assertion の強化のみ）。
- 本レビューは**承認ではない**。実キー評価と有効化判断は人間が行う。
