# AI 限定パイロット運用（B 案・1〜2 プロジェクト）

- 版: v1.0（2026-11-13）
- 位置づけ: [既定 ON 判断ブリーフ](../verification/2026-11-13-ai-enablement-decision-brief.md) の **B（限定パイロット）** を
  実行するための手順。**2026-11-13 に本番配備済み**（[配備記録](../verification/2026-11-13-ai-pilot-deployment.md)）。
- 対象: 03 討論 / 04 批判 / 05 候補（Phase 3 B/C）。既存の AI 下書き（`ai.draft_requested`）は対象外。

## 1. 目的と範囲

- 本番に AI 支援を配備するが、**既定 OFF を維持**し、対象プロジェクトを 1〜2 件に限定する。
- 期間: 1〜2 週間を想定（対象と期間は所有者が決める）。
- 観測: 品質（人間レビュー）、失敗率、レイテンシ、トークン/費用、監査。
- 非範囲: 全プロジェクト展開（C）、既定 ON 化、モデル変更。

## 2. 限定の仕組み

- 環境変数 `RIHRP_LLM_ALLOWED_PROJECTS`（カンマ区切りのプロジェクト ID）。
  - 空（既定）: 制限なし（従来どおり。ただし `RIHRP_LLM_*` 未設定なら 503）。
  - 設定時: リストに無いプロジェクトの **03/04/05 の生成 API** は **403 `ai_not_allowed`**。
  - AI 下書き（`ai.draft-claims`）は対象外（既存機能を巻き込まない）。
- プロジェクト ID: 画面 URL の `/projects/<id>`、または `GET /api/projects` の `id`。
- 実装: `apps/api/rihrp/routers/ai.py` の `_ensure_ai_allowed`（PR #66）。テストで 403/200 を固定。

## 3. 前提と承認

| 項目 | 内容 |
|---|---|
| 本番配備 | **人間の明示承認**が必要（リリース手順に従う） |
| キー | 本番の `RIHRP_LLM_*` は AI 下書きで設定済み（2026-11-12 リリース）。新規 secret は不要 |
| 対象 | `68489ee7a6ee4d1999d07719673d81fd`（「護岸の洗掘抑制」）。1 件で開始 |
| 観測者 | 週次の監査・費用確認を行う人（所有者または指名者） |
| 停止条件 | 捏造引用・注入追従・監査混入・費用上限超過・5xx 増加 |

## 4. 配備手順（概要）

1. 対象 SHA が `main` にマージ済みで CI 成功していることを確認する。
2. [Native コミット別リリース](../runbooks/immutable-release.md) に従い、build → 隔離起動・受入 →
   最新バックアップの実復元証跡 → activate を行う（DB migration の追加は無し）。
3. 本番の EnvironmentFile（既存 `RIHRP_LLM_*` と同じ場所）に
   `RIHRP_LLM_ALLOWED_PROJECTS=<id1>,<id2>` を追加してサービスを再起動する。
4. 配備後の確認（§5）を行う。

## 5. 配備後の確認

- `/healthz` / `/readyz` が 200、`release.sha` が対象 SHA と一致。
- 許可プロジェクト: 03/04/05 を各 1 回生成し、200 と `meta.tokens` を確認（合計 3 リクエスト・約 $0.1）。
- 非許可プロジェクト: 03/04/05 が **403 `ai_not_allowed`**。
- 監査: `ai.debate_requested` / `ai.critique_requested` / `ai.candidate_requested` に
  provider/model/prompt_version/件数/latency/tokens があり、本文・鍵が無い。
- AI 下書きが従来どおり動く（allowlist の影響を受けない）。

## 6. 観測（週次）

- 監査から `ai.*` の件数・失敗（4xx/5xx）・平均 latency・tokens を集計する。
- 費用は tokens × 単価（Opus 5.5: input $4 / output $20 per MTok）で算出し、Console と照合する。
- 品質は対象プロジェクトの研究文書を人間がレビュー（捏造引用・根拠不支持・注入の痕跡）。
- 停止条件に該当したら §7 に従う。

## 7. 停止・切戻し

1. **新機能だけ止める**: `RIHRP_LLM_ALLOWED_PROJECTS=__disabled__`（どのプロジェクトにも一致しない）にして再起動。
   03/04/05 は全プロジェクトで 403。AI 下書きは影響を受けない。
2. **リリースを戻す**: `tools/release_activate.py rollback --expect-sha <旧SHA>`（配備手順の切戻し）。
3. **キーを止める**: 全 AI を止めたい場合のみ `RIHRP_LLM_API_KEY` を外す（AI 下書きも止まる）。

## 8. 既知の UX 制約

- 非許可プロジェクトでも AI ボタンは表示され、押すと 403 のトーストが出る（ボタンの非表示は未実装）。
- パイロット中は許容し、必要なら「AI 可否を文書 API で返してボタンを隠す」を次期対応とする。

## 9. 未確定（所有者が決める）

| ID | 決めること |
|---|---|
| P1 | 対象プロジェクト（**決定済み**: `68489ee7a6ee4d1999d07719673d81fd`） |
| P2 | 観測期間（例: 2 週間） |
| P3 | 週次確認の担当者 |
| P4 | 配備日時と承認（**完了**: 2026-11-13 16:20 JST・承認済み） |
