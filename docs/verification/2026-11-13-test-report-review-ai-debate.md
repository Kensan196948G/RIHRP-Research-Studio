# AI 討論 PoC 検証記録のレビュー（2026-11-13・test-report-review 適用）

- **review_type: AI-assisted recommendation**
- **evidence_state: conditionally_evidence_consistent**
- **recommendation: conditional_pass**
- **human_final_decision: pending**
- confidence: medium（記録作成者とレビュアーが同一 Agent。実キー評価は未供給）
- 適用: `test-report-review` Skill（記録作成時の**事後適用**。本文書がその記録）
- 対象: PR #50 `feat/ai-debate-poc` の検証記録（コード・テスト状態 `8f90327`）

## 1. Review Status

対象は [2026-11-13-ai-debate-poc.md](2026-11-13-ai-debate-poc.md) の主張（API 11 件・E2E 1 件・全 E2E 44 件・
vitest 10 件・既定 OFF・引用ガード・監査）。実行証跡（pytest / CI / E2E ログ）は存在し、主要な数値は
一致する。欠陥証跡（欠陥一覧）は供給されていない。実キーでの P0/P1 検証はテスト計画で
`out_of_scope` と明記され、記録も未実施と申告している。ブロッカーは無く、条件付きで整合と判定する。

## 2. Sources and Versions

| ID | 種別 | 版・識別子 | 役割 | 可用性 |
|---|---|---|---|---|
| S1 | 検証記録 | `docs/verification/2026-11-13-ai-debate-poc.md`（`8f90327`） | 検証報告 | あり |
| S2 | テスト計画 | `docs/testing/06-ai-debate-test-plan.md`（`8fda9aa`） | 範囲・LHT/D ケース | あり |
| S3 | API テスト | `tests/integration/test_ai_debate.py`（11 tests, `8f90327` + 本レビューで assertion 強化） | 実行・ケース定義 | あり |
| S4 | E2E 実行証跡 | `docs/verification/2026-11-13-ai-debate-poc/e2e-full.txt`（SHA-256 `21475a48…`）、`e2e-ai-debate.txt`（`258b17e5…`）、`e2e-full-failed-1st.txt`（`8822dfa9…`） | 実行ログ | あり（2026-11-13 09:33 / 09:37 / 09:42〜09:44 JST） |
| S5 | CI | run `43344307954`（`8f90327`, 2026-11-13T01:21Z） | 実行証跡 | あり（3 ジョブ success） |
| S6 | Web テスト | `npx vitest run` ローカル実行（2026-11-13 10:25 JST） | 実行証跡 | あり（10 passed） |
| S7 | 欠陥証跡 | `docs/verification/2026-11-13-ai-debate-poc.md`「既知の問題・欠陥」 | 欠陥一覧 | **not supplied → 追補で明示（C2 closed）** |
| S8 | 実キー評価 | — | 品質・注入・棄権 | **not supplied**（人間承認待ち） |
| S9 | テスト品質レビュー | [2026-11-13-ai-generated-test-review.md](2026-11-13-ai-generated-test-review.md) | テスト自体の点検 | あり |

## 3. Evidence Consistency Matrix

| 主張（S1） | 証跡 | 判定 | 影響 |
|---|---|---|---|
| API `test_ai_debate.py` 11 passed | S3 ローカル実行 11 passed（10:2x JST）、S5 API ジョブ success | aligned | なし |
| 既存 AI 下書き 11 passed（回帰） | S3 実行 11 passed、S5 全 pytest success | aligned | なし |
| 討論 E2E 1 passed（4.0s） | S4 `e2e-ai-debate.txt` 4.0s（単体）、`e2e-full.txt` 3.8s | aligned（実行ごとの差） | なし |
| 全 E2E 44 passed / 1 skipped / 2.2 分 | S4 `e2e-full.txt`（45 tests / 44 passed / 1 skipped / 2.2m）。初回の 3 failed は E2E 中の pytest 同時実行が原因と特定（D-02・再発防止済み） | aligned | skip はスタブ設定時の未設定経路（意図どおり） |
| Web build OK / vitest 10 passed | S5 Web ジョブ success、S6 vitest 10 passed | aligned（件数はローカル） | なし |
| 403 / 503 / 422 / 未知 ID / 混在 / 401 / 不正 JSON / timeout / 429 / 監査 | S3 各テスト。**「401」は上流 401**（利用者認証 401 は未テスト） | **partially aligned（表現の曖昧さ）** | 認証境界の未テストを「401 済み」と誤読しうる → 本文表現を修正 |
| 引用ガード（未知 ID 破棄・全滅 502） | S3 未知 ID／混在テスト（本レビューで混在の assertion を強化） | aligned | なし |
| 監査は本文・プロンプト・鍵を残さない | S3 監査テスト（本レビューでメタデータ検証を追加） | aligned | なし |
| 既定 OFF（キー未設定は 503） | S3 503 テスト | aligned | 外部通信の不在自体は未検証（P2） |
| 実キーのスモーク未実施 | S8 なし（S1/S2 が明記） | aligned（申告どおり） | 条件 C1 |
| P0/P1 の実キー検証（LHT-02〜06）未実行 | S2 で `out_of_scope`、S1 で未実施と明記 | aligned（範囲宣言あり） | 条件 C1 |
| 欠陥 0 件（暗黙） | S7 なし（レビュー時）→ 追補で「既知の問題・欠陥」を明示 | **missing → aligned（追補）** | C2 closed |

## 4. Tested and Untested Scope

- **承認された範囲（PR 目的）**: スタジオ 03 討論の AI 支援 PoC。既定 OFF・採用時のみ保存。実キーは CI 外。
- **実行済み**: API 11 ケース（成功・403・503・422・未知 ID・混在 ID・上流 401・不正 JSON・timeout・429・監査）、
  討論 E2E 1 ケース、全 E2E 回帰 44 ケース、vitest 10、CI 3 ジョブ、ruff / OpenAPI drift。
- **承認済み除外（S2）**: 実キー投入・本番配信・自動品質ゲート。実キーは「人間の承認後のスモーク 1 回」に限定。
- **申告済み未実施**: LHT-02/03/04/05/06、D-13〜D-16、品質ルーブリックの評定者・閾値、実キーでの棄権・注入。
- **不明・隠れた範囲**: なし（追加で判明したのは「討論 E2E が手動ワークフローで skip される」環境差で、S1 に追記した）。
  利用者認証 401 と破棄経路は未テストとして明示した。

## 5. Contradictions

| 対象 | 差分 | 影響 | 解消主体 |
|---|---|---|---|
| PR 本文 / S1 の「401」 | 実体は**上流 401** の変換テスト。利用者認証の 401 は未テスト | 「401 を検証済み」と読める | 本文を「上流 401」に修正（実施） |
| S1 の E2E 4.0s | 全 E2E 実行では 3.8s | なし（同一テスト・別実行） | 解消不要 |
| S1 の全 E2E 44 passed | CI 手動 E2E では討論 spec が skip される | 環境差であり矛盾ではない。証跡の再現手順が暗黙 | S1 に実行手順と限界を追記（実施） |

## 6. Blockers and Conditions

**Blockers: なし。**

理由: 実行証跡と主張は主要部分で一致し、未実施の P0（注入）はテスト計画で `out_of_scope` と宣言され、
記録も実キー未実施を明記している。既定 OFF のため本 PR は本番挙動を変えず、「実キーで安全」という主張は
どこにも存在しない。したがって「未検証の P0 が記録の主要結論を支えていない」状態であり、ブロッカーではない。

| ID | 条件 | 状態 | owner | 終了条件（証跡） |
|---|---|---|---|---|
| C1 | 実キー評価（LHT-02/03/04/05/06・D-13〜16）が未実施 | **closed**（2026-11-13・評定 1 名目） | オーナー（承認）/ QA / セキュリティ | [canary 記録](2026-11-13-ai-debate-canary.md): 3 リクエスト・G1/G2/G4 PASS・監査確認済み。2 名目評定は A5 |
| C2 | 欠陥証跡（欠陥一覧・オープン欠陥の明示）がない | **closed**（2026-11-13 追補） | QA | 検証記録「既知の問題・欠陥」にオープン欠陥 0 件と D-01〜D-03 を明示 |
| C3 | 討論 E2E が標準 E2E ワークフローで実行されない（スタブ未配線） | **closed**（2026-11-13） | 開発（適用は人間） | PR #58 で適用し、run `43368903919` = 46 passed / 1 skipped（AI 討論・批判・候補の 3 spec 実行）を確認 |

**Improvements**: 未認証 401・破棄経路・`evidenceIds` 保存・スキーマ破棄・`rate_limited` code のテスト追加（任意）。

## 7. Residual Risks

| リスク | 影響 | 現状の統制 | 限界 |
|---|---|---|---|
| 実キーでの幻覚・注入（LHT-05 は P0） | 誤情報の混入・資料内命令への追従 | 既定 OFF、引用 ID 実在チェック、人間承認ゲート | 実キー証跡なし。実在 ID でも**支持関係**は未保証 |
| 引用 ID 実在 ≠ 内容支持 | 誤った引用が残る | 人間レビュー前提 | 自動検出なし（LHT-02/03/06） |
| レート制限がプロセス内 | 多プロセス配備で実効性低下 | 1 分窓のプロセス内制限 | 共有ストアなし |
| E2E が CI 未配線 | 討論 UI の退行を CI で検知できない | スタブ配線済み（CI で 46 passed / 1 skipped） | なし（C3 closed） |
| 作成者＝レビュアー | 見落としの独立性がない | Skill の観点適用 | 第三者レビューではない |

## 8. Open Actions

| ID | 対象 | 内容 | owner | 終了条件 | 状態 |
|---|---|---|---|---|---|
| A1 | C1 | 実キー評価（承認後） | オーナー / QA | 評定記録＋監査 | open |
| A2 | C2 | 欠陥一覧の明示 | QA | 記録更新 | **closed**（2026-11-13） |
| A3 | C3 | E2E スタブ配線 | 開発（適用は人間） | 適用済み・run 43368903919 で PASS | **closed**（2026-11-13） |
| A4 | 改善 | 401・破棄・スキーマ等の追加テスト | 開発 | テスト追加 | **closed**（2026-11-13・PR #53） |
| A5 | C1 | 評定 2 名目と合格ライン（Q6）の確定 | オーナー | 2 名目（AI 再評定・独立性限定的）と Q6=既定案を記録 | **closed**（2026-11-13） |

## 9. Recommendation Basis and Limitations

- 実行証跡（pytest / CI / E2E ログ / vitest）が存在し、S1 の主要数値は実測と一致する。
- 未実施の最重要項目（実キー・P0 注入）は**範囲外と宣言済み**で、既定 OFF のため本 PR の結論
  （スタブ検証・既存不変・採用時のみ保存）を支える必要がない。よってブロッカーではない。
- 一方、実キー評価・欠陥証跡・E2E 配線は閉鎖条件と owner を定義できるため **conditional_pass**。
- 限界: 実装・テスト・レビューが同一 Agent。実キー品質は未評価。C1 の証跡が揃うまで「安全」とは言えない。
- 本書は**承認ではない**。`human_final_decision: pending`。

## 10. Human Decision Questions

1. 既定 OFF の PoC として本 PR をマージし、実キー評価（C1）を**有効化前のゲート**として残してよいか。
2. 実キー評価の実施者・承認者・評定ルーブリックをいつ確定するか。
3. （解決済み）C3 の E2E スタブ配線は 2026-11-13 に適用し、run 43368903919 で PASS。
