# AI 批判・候補提案 検証記録のレビュー（2026-11-13・test-report-review 適用）

- **review_type: AI-assisted recommendation**
- **evidence_state: conditionally_evidence_consistent**
- **recommendation: conditional_pass**
- **human_final_decision: pending**
- confidence: medium（記録作成者とレビュアーが同一 Agent。実キー評価は未供給）
- 適用: `test-report-review` Skill（記録作成時の**事後適用**。本文書がその記録）
- 対象: [検証記録](2026-11-13-ai-critique-candidate.md)（コード・テスト状態: 本 PR head）

## 1. Review Status

対象は Phase 3 C（04 批判・05 候補の AI 提案）の検証記録。実行証跡（pytest / E2E / CI）は存在し、
主要な数値は実測と一致する。欠陥証跡は供給されていない。実キー評価は未実施で、テスト計画で
`out_of_scope` と宣言されている。ブロッカーは無く、条件付きで整合と判定する。

## 2. Sources and Versions

| ID | 種別 | 版・識別子 | 役割 | 可用性 |
|---|---|---|---|---|
| S1 | 検証記録 | `docs/verification/2026-11-13-ai-critique-candidate.md`（本 PR） | 検証報告 | あり |
| S2 | テスト計画 | `docs/testing/08-ai-critique-candidate-test-plan.md` | 範囲・ケース | あり |
| S3 | API テスト | `tests/integration/test_ai_critique_candidate.py`（13 tests） | 実行・ケース定義 | あり |
| S4 | E2E 実行証跡 | `docs/verification/2026-11-13-ai-critique-candidate/e2e-full.txt`（SHA-256 `ba663a0c…`）、`api-tests.txt`（`028a61a2…`） | 実行ログ | あり（2026-11-13 12:36〜12:52 JST） |
| S5 | CI | 本 PR の CI（マージ前） | 実行証跡 | PR 作成後に追記 |
| S6 | 欠陥証跡 | 「既知の問題・欠陥」節 | 欠陥一覧 | あり（オープンな製品欠陥 0 件） |
| S7 | 実キー評価 | — | 品質・注入・棄権 | **not supplied**（承認待ち） |

## 3. Evidence Consistency Matrix

| 主張（S1） | 証跡 | 判定 | 影響 |
|---|---|---|---|
| API 13 passed | S3/S4 `api-tests.txt` | aligned | なし |
| 全 pytest 434 passed / 1 skipped | S4、ローカル実行 | aligned | なし |
| 討論 E2E 2 passed / 全 E2E 46 passed / 1 skipped | S4 `e2e-full.txt`（47 tests） | aligned | なし |
| AI の採点値を破棄 | S3 C-07（scores/total/status 非含有） | aligned | なし |
| 採用後に既存ロジックで採点 | S4 A-02（scores/total が付与） | aligned | なし |
| 未知 ID/type/vars の破棄 | S3 C-02/C-03/C-08 | aligned | なし |
| 監査に本文・鍵なし | S3 C-06 | aligned | なし |
| 既定 OFF（503） | S3 C-13 | aligned | なし |
| 実キー評価 未実施 | S7 なし（S2 が out_of_scope） | aligned（申告どおり） | 条件 C1 |
| 欠陥 0 件 | S6（オープン 0 件・停止条件該当なし） | aligned | なし |

## 4. Tested and Untested Scope

- **承認された範囲**: Phase 3 C の API と UI（生成のみ・既定 OFF・AI は採点しない）。
- **実行済み**: API 13 ケース、E2E 2 ケース、全 pytest、全 E2E、build、vitest。
- **承認済み除外**: 実キー投入・本番配信（テスト計画 08 の `out_of_scope`）。
- **申告済み未実施**: LHT-C4（根拠支持関係）、LHT-C5（棄権）、LHT-C6（注入）、2 名評定。
- **不明・隠れた範囲**: なし（手動 E2E のスタブ未配線は C3 として管理し、2026-11-13 に解消）。

## 5. Contradictions

なし。E2E の実行時間・件数は実行ログと一致する。

## 6. Blockers and Conditions

**Blockers: なし。**

理由: 主要な結論（生成のみ・AI 採点なし・未知値の破棄・既定 OFF）はスタブ実行証跡で支持される。
実キー P0（注入）はテスト計画で範囲外と宣言され、記録も未実施と明示している。既定 OFF のため
本 PR は本番挙動を変えず、「実キーで安全」という主張は存在しない。

| ID | 条件 | 状態 | owner | 終了条件（証跡） |
|---|---|---|---|---|
| C1 | 実キー評価（LHT-C4/C5/C6・評定）が未実施 | **open** | オーナー（承認）/ QA | 実キーでスモーク 1 回＋評定＋監査記録。**有効化前に必須** |
| C2 | E2E が手動ワークフローで skip（スタブ未配線） | **closed**（2026-11-13） | 開発（適用は人間） | PR #58 で適用し、run `43368903919` = 46 passed / 1 skipped（`ai-assist.spec.ts` の 2 件も実行） |

## 7. Residual Risks

| リスク | 影響 | 現状の統制 | 限界 |
|---|---|---|---|
| 実キーでの幻覚・注入 | 誤った批判・候補 | 既定 OFF、引用 ID 実在チェック、人間採用 | 実キー証跡なし。文面の正しさは人間レビュー |
| AI 文面の意味的妥当性 | もっともらしいが誤った候補 | 既存採点は文面から決定論的に計算 | 文面そのものの真偽は保証しない |
| 候補の採点は文面依存 | 文面次第でスコアが変わる | 同一文面なら同一スコア（決定論） | AI の文面選択は非決定的 |
| E2E が CI 未配線 | UI 退行の検知漏れ | スタブ配線済み（CI で 46 passed / 1 skipped） | なし（C2 closed） |
| 作成者＝レビュアー | 見落としの独立性がない | Skill の観点適用 | 第三者レビューではない |

## 8. Open Actions

| ID | 対象 | 内容 | owner | 終了条件 | 状態 |
|---|---|---|---|---|---|
| A1 | C1 | 実キー評価（承認後） | オーナー / QA | 評定記録＋監査 | open |
| A2 | C2 | E2E スタブ配線（討論と共通） | 開発（適用は人間） | 適用済み・run 43368903919 で PASS | **closed**（2026-11-13） |
| A3 | 改善 | 評価用の固定フィクスチャ拡充（分野別） | 開発 | ケース追加 | open（任意） |

## 9. Recommendation Basis and Limitations

- 実行証跡が存在し、S1 の主要数値は実測と一致する。AI 採点の破棄と採用後採点は API/E2E の両方で固定。
- 未実施の最重要項目（実キー P0）は範囲外と宣言され、既定 OFF のため本 PR の結論を支える必要がない。
- 実キー評価・E2E 配線は閉鎖条件と owner を定義できるため **conditional_pass**。
- 限界: 実装・テスト・レビューが同一 Agent。実キー品質は未評価。
- 本書は**承認ではない**。`human_final_decision: pending`。

## 10. Human Decision Questions

1. 既定 OFF の PoC として本 PR をマージし、実キー評価（C1）を有効化前のゲートとして残してよいか。
2. E2E スタブ配線（C2）をいつ適用するか（討論と同じパッチ）。
