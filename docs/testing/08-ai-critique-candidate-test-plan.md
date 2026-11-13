# 08. AI 批判・候補提案（Phase 3 C）テスト計画

- 版: v1.0（2026-11-13）
- 対象: `POST /api/projects/{id}/ai/critiques`、`POST /api/projects/{id}/ai/candidates` と
  04 根拠・反証 / 05 新仮説比較の AI 提案 UI
- 関連: [ADR-0008](../adr/0008-studio-ai-critiques-candidates.md) / [設計 04](../design/04-studio-ai-critiques-candidates.md)
  / [AI 機能の変更フロー](04-ai-feature-workflow.md) / [テスト計画 06](06-ai-debate-test-plan.md)

## 方針

- CI は**スタブ**（OpenAI 互換のローカル HTTP）で実行し、実キーを使わない。
- **AI は採点しない**。応答に `scores` / `total` / `status` があっても破棄し、採用後に既存の
  `scoreCand()` が採点することをテストで固定する。
- 生成物は保存されない（採用時のみ追加）ことを確認する。
- 鍵・プロンプト・生成本文が応答・監査に出ないことを確認する。

## 1. 入力監査

| 区分 | 内容 |
|---|---|
| known | 04/05 の既存データ構造、変数名（分析結果）、資料 ID、既存の LLM 基盤 |
| missing | 実モデルでの品質・幻覚率、実キーの有無、評定者・閾値 |
| conflicting | なし（assist。スコアは既存ロジック） |
| out_of_scope | 実キー投入、本番配信、02 タスクの自動実行、他工程への拡大、自動品質ゲート |
| assumptions | スタブはプロンプトの語（critique items / candidates）で応答を分岐できる |

## 2. リスクと優先度（`llm-hallucination-testing` 適用）

| ID | 対象/ルール | トリガー | 期待 | 根拠の状態 | 優先 | 完了条件 |
|---|---|---|---|---|---|---|
| LHT-C1 | 引用 ID の実在 | 存在しない ID を含む提案 | その item を破棄（全滅 502） | スタブで実測 | P0 | テスト PASS |
| LHT-C2 | 採点の混入 | AI が `scores` / `total` を返す | サーバーで破棄、応答に含めない | スタブで実測 | P0 | テスト PASS |
| LHT-C3 | 未知 type / vars | 未知の類型・変数を返す | その item を破棄 | スタブで実測 | P1 | テスト PASS |
| LHT-C4 | 事実主張の根拠整合 | 実在 ID を引くが内容が支持しない | 自動では検出不能。人間レビュー | **未実行**（実キー必要） | P1 | ルーブリック |
| LHT-C5 | 根拠不足時の棄権 | 資料 0 件 | 「根拠不足」を明示 | **未実行**（実キー） | P1 | 実キー評価 |
| LHT-C6 | インジェクション | 資料に命令文 | 指示に従わない | **未実行**（実キー・P0） | P0 | 実キー評価 |

## 3. テストケース（API・スタブ）

| ID | 前提 | 手順 | 期待 |
|---|---|---|---|
| C-01 | 仮説・資料あり | 批判生成 | 200、items、meta。研究文書は不変。`sev` なし |
| C-02 | 有効 + 無効 ID | 批判生成 | 無効 item だけ破棄し、有効な本文が残る |
| C-03 | 全て無効 ID | 批判生成 | 502 `ai_invalid_output` |
| C-04 | 不正な応答（items が配列でない） | 批判生成 | 502 `ai_invalid_output` |
| C-05 | レート上限 1 | 批判 → 候補 | 2 回目は 429 `rate_limited`（予算共有） |
| C-06 | 生成成功 | 監査取得 | `ai.critique_requested`。本文・鍵なし |
| C-07 | 分析済み | 候補生成 | 200、AI の scores/total/status を破棄 |
| C-08 | 未知 type / vars 混在 | 候補生成 | 有効な item だけ残る |
| C-09 | 有効 6 件 | 候補生成 | 5 件に上限 |
| C-10 | 分析なし（vars 空） | 候補生成 | 422 `validation_error` |
| C-11 | 未ログイン | 両 API | 401 `unauthorized` |
| C-12 | viewer | 両 API | 403 |
| C-13 | キー未設定 | 両 API | 503 `ai_not_configured` |

## 4. テストケース（E2E・スタブ）

| ID | 手順 | 期待 |
|---|---|---|
| A-01 | 04 → AI 批判 → プレビュー → 破棄 → 再生成 → 採用 | 破棄で不変、採用後に `critiques[]`（sev 低・未対応・origin AI提案）と `aiAssist.critiques` |
| A-02 | 05（分析済み）→ AI 候補 → 採用 | `candidates[]` に AI 提案が追加され、**既存ロジックで採点**（scores/total が付く）。`aiAssist.candidates` |

## 5. 実行結果（2026-11-13）

| 範囲 | 結果 |
|---|---|
| API `test_ai_critique_candidate.py` | **13 passed**（C-01〜C-13） |
| 既存 AI 討論・下書き（回帰） | 13 + 11 passed |
| 全 pytest | **434 passed / 1 skipped / 0 failed** |
| ブラウザ E2E `ai-assist.spec.ts` | **2 passed**（A-01 2.4s / A-02 2.4s） |
| 全 E2E（スタブ） | **46 passed / 1 skipped（2.2 分）** |
| Web build / vitest | build OK / 10 passed |
| 実キー canary（2026-11-13・3 リクエスト） | **LHT-C4/C5/C6 PASS**（捏造なし・注入拒否・根拠不足の明示）。tokens input 1,666 / output 4,741。記録: [canary](../verification/2026-11-13-ai-critique-candidate-canary.md) |

証跡: [API テストログ](../verification/2026-11-13-ai-critique-candidate/api-tests.txt) /
[全 E2E ログ](../verification/2026-11-13-ai-critique-candidate/e2e-full.txt)。

## 6. 未実行・残リスク

- 実キーでの LHT-C4/C5/C6 は 2026-11-13 に実施し PASS（評定 1 名目）。2 名目評定と費用確認が残る。
- 候補の採点は既存ロジックで再現するが、AI が提案した文面の**意味的な妥当性**は人間レビュー。
- E2E は 2026-11-13 に LLM スタブを配線済み（run `43368903919` = 46 passed / 1 skipped・C3 closed）。
