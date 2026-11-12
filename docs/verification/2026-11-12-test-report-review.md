# 2026-11-12 テスト検証記録のレビュー（test-report-review 適用・事後）

- **review_type: AI-assisted recommendation**
- **evidence_state: conditionally_evidence_consistent**
- **recommendation: conditional_pass**
- **human_final_decision: pending**
- confidence: medium（記録の作成者とレビュアーが同一のため独立性は限定的）
- 適用: `test-report-review` Skill（実装時ではなく**事後適用**。本文書がその記録）

## 1. Review Status

対象は 2026-11-12 の (a) 実AI検証、(b) Anthropic スモーク、(c) 本番配備記録の3文書。
実行証跡（pytest/CI/health/alerts/journal）と欠陥証跡（httpx 起因の 25 分 readyz 503）は存在し、
主要な主張は整合する。ただし一部の数値が**会話ログのみ**で保存証跡がなく、本番ブラウザ受入は未実施。
ブロッカーは無く、条件付きで整合と判定する。

## 2. Sources and Versions

| ID | 種別 | 版・識別子 | 役割 | 可用性 |
|---|---|---|---|---|
| S1 | 実AI検証記録 | `docs/verification/2026-11-12-real-ai-verification.md`（#29） | 検証報告 | あり |
| S2 | Anthropic スモーク記録 | `docs/verification/2026-11-12-anthropic-smoke.md`（#33） | 検証報告 | あり（数値の保存証跡なし） |
| S3 | 本番配備記録 | `docs/verification/2026-11-12-production-ai-release.md`（#37/#38） | 配備報告 | あり |
| S4 | 実行証跡 JSON | `docs/verification/2026-11-12-real-ai/*.json` | 生データ | あり |
| S5 | CI / PR | run 43210680241 ほか、PR #29〜#38 | 実行証跡 | あり |
| S6 | 稼働実測 | `/healthz` `/readyz`、`journalctl`、`alerts.log`、`transitions/` | 実行証跡 | レビュー時に取得 |
| S7 | 本番ブラウザ受入 | — | 受入 | **not supplied** |

## 3. Evidence Consistency Matrix

| 主張（S1/S2/S3） | 証跡 | 判定 | 影響 |
|---|---|---|---|
| Part A 24/24 | S4 `results.json`（8/6/6/4） | aligned（表現を修正済み） | 軽微 |
| 自然引用 0/6・逐語 6/6 | S4 `free_results.json` | aligned | なし |
| 改竄 2/2 | S4 `tamper_results.json` | aligned | なし |
| 丸め 6/6 unverified | S4 `rounding_results.json` | aligned | なし |
| Anthropic 200 / 3.9 秒 / 3 候補 | 会話ログ。再実行の保存証跡 `production_ai_smoke.json`（200 / 4.9 秒 / 2 候補） | **aligned（再実行で確認。元値はログ由来）** | 条件 C2 を解消 |
| 本番AI 200 / 4.4 秒 / 2 候補 | 同上（再実行 4.9 秒 / 2 候補、監査 `ai.draft_requested` 付き） | **aligned（再実行で確認）** | 条件 C2 を解消 |
| migration 0005 適用・列追加 | `migration_0005_check.json`（読み取り専用 psql） | **aligned** | 解消済み |
| readyz 503 25 分・5 回通知 | S6 `alerts.log`（20:21/20:26/20:31/20:37/20:42） | aligned | なし |
| httpx 欠落が原因 | S6 journal（ModuleNotFoundError） | aligned | なし |
| CI green | S5 | aligned | なし |
| 切戻し訓練・停止 5 秒/4 秒 | S6 journal（20:52:07→12 / 20:52:21→25） | aligned（追記済み） | なし |
| 本番 DB へ書込みなし | コピー DB 使用（S3 §3） | aligned（方式による） | なし |
| 本番ブラウザ受入 | S7 なし | **missing** | 条件 C1 |

## 4. Tested and Untested Scope

- **承認された範囲**: サーバー側 AI 下書き、AI 支援レポートの承認条件、migration 0005 の本番配備。
- **実行済み**: pytest 408 / CI 3 ジョブ / 隔離 E2E（スタブ・実AI）/ 本番 health・ready / 切戻し訓練。
- **承認済み除外**: なし。
- **未実施（記録済み）**: 本番ブラウザでの人間受入、DB 復元を伴う 0004 切戻し。
- **不明・隠れた範囲**: 本番データを用いた AI 呼び出し（設計上、複製 DB のみ）。批判的未検証ではない。

## 5. Contradictions

なし。唯一の曖昧さは S1 の「24/24」が
「意図した判定」と「入口拒否による経路一致」を混在させていた点で、本文書のレビューで
「経路一致 24/24・エンジン到達 18/18」に修正した。

## 6. Blockers and Conditions

**Blockers: なし。**

| ID | 条件 | 状態 | 終了条件 |
|---|---|---|---|
| C1 | 本番ブラウザ受入が未実施 | **open** | 本番で「AI で下書き」が成功し、監査に `ai.draft_requested` が残る（証跡: 画面/監査） |
| C2 | スモーク数値・migration 確認が会話ログのみ | **closed** | `production_ai_smoke.json` と `migration_0005_check.json` を保存（2026-11-12 21:44） |
| C3 | 「24/24」の定義が曖昧 | **closed** | 本レビューで表現を修正（`18/18` を併記） |
| C4 | 切替停止時間が未計測 | **closed** | journal から 5 秒/4 秒を実測し追記 |

**Improvements**: 受入チェックリストの文書化、コスト上限の監視追加。

## 7. Residual Risks

| リスク | 影響 | 現状の統制 | 限界 |
|---|---|---|---|
| 本番 AI は複製 DB でのみ実測 | 本番データでの挙動は未確認 | 同一リリース・同一設定で検証 | データ依存の差異は未評価 |
| 0004 への切戻しは DB 復元が必要 | 復旧にデータ損失 | 0005 対応リリースへの再 activate を用意 | DB 復元訓練は未実施 |
| レート制限がプロセス内 | 多プロセス配備で無効化 | 5 回/分（単一プロセス） | 共有ストア未実装 |
| Anthropic の費用・quota 未監視 | 上限超過・停止 | 1 回上限と回数上限のみ | 日次上限・警報なし |
| healthcheck はローカル記録のみ | 障害通知が届かない | alerts.log | 外部通知なし |

## 8. Open Actions

| ID | 対象 | 内容 | owner | 終了条件 | 状態 |
|---|---|---|---|---|---|
| A1 | C1 | 本番ブラウザ受入 | オーナー | 受入成功＋監査記録 | open |
| A2 | C2 | スモーク/migration 証跡の保存 | AI | JSON をコミットし文書から参照 | **closed** |
| A3 | 残リスク | 費用・quota の日次上限と警報 | 未定 | 設定と実測 | open（任意） |
| A4 | 残リスク | 外部通知の追加 | 未定 | 通知到達の実測 | open（任意） |

## 9. Recommendation Basis and Limitations

- 実行証跡・欠陥証跡ともに存在し、主要な結論（本番稼働・AI 実動作・切戻し可能性）は支持される。
- ブロッカーは無い。C2（証跡保存）は再実行の保存証跡で閉鎖した。残る条件は C1（人間受入）のみで、閉鎖条件と証跡が定義できるため **conditional_pass**。
- 限界: 記録作成者とレビュアーが同一。C2 は再実行の保存証跡で閉鎖したが、**元の 3.9 秒/4.4 秒は会話ログ由来**で、再実行値（4.9 秒）とは別。
- 本書は**承認ではない**。`human_final_decision: pending`。

## 10. Human Decision Questions

1. 複製 DB での AI 実測と隔離 E2E を、本番 AI の十分な証跡として受容するか。
2. 0004 切戻しが DB 復元を要する現状を受容するか、0005 専用の切戻しリリースを用意するか。
3. 費用上限・外部通知を今回のリリース条件に含めるか、次回改善とするか。
