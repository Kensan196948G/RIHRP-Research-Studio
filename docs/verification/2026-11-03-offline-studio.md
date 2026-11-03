# 検証記録 — 2026-11-03 Offline Research Studio WebUI（PR #5・レビュー3巡）

環境: ローカル Linux、Python 3.12、Node 22、PostgreSQL 16（`rihrp_test*`）、systemd --user。
対象ブランチ: `feat/offline-studio-ui`（PR #5、base=`main`）。

## 1. サマリ

| 項目 | 結果 |
|---|---|
| レビュー1巡目 | fail（High 2 / Medium 2 / Low 3）→ head `8528d84` |
| レビュー2巡目 | fail（High 1 / Medium 3 / Low 4）→ head `674e58e` |
| 修正 | `a7ad639`（2巡目の全 8 件を修正） |
| 自動テスト | pytest **135 passed / 1 skipped**、vitest **10 passed**、Playwright **21 passed**（46.2s） |
| 静的検査 | `tsc -b` / `vite build` / `ruff check apps/api tests` / `ruff format --check apps/api tests` / `openapi --check` すべて pass |
| CI | run `41560328053`（head `a7ad639`）**success** |

## 2. レビュー2巡目の指摘と対応（`a7ad639`）

| # | 重要度 | 指摘 | 対応 |
|---|---|---|---|
| 1 | High | 比較・根拠画面の保存型 XSS（`viewCompare` / `rankHTML` の `candidate.label`、`evidence` / `critique` / `candidate` の id、plan measure role が未エスケープ） | 全動的文字列・属性を `esc()`、id を `safeId()` で `[A-Za-z0-9_-]` に正規化。E2E「保存済みデータ由来の XSS が成立しない」で compare / evidence 経路も拘束（`[data-injected]` 0 件・`img[src="x"]` 0 件・`window.__xss` 未定義） |
| 2 | Medium | AbortController が API 通信へ伝播せず、中止後もプロジェクト作成 | `request()` が `signal` を `fetch` へ伝播。list/get/create/save/rename/delete 全てに伝播。中止時の孤児プロジェクトを削除。unmount 時の flush は signal を切り離し（`detached`）、遷移で保存待ちを失わない |
| 3 | Medium | `destroy` が未追跡 `setTimeout` を残し unmount 後も処理が進行 | 生の `setTimeout` を `later()` に統一（残存は `later` 内と討論再生の interval のみ）。`destroy` で `clearInterval`（interval）/ `clearTimeout`（timeout）に整理し、`playDebate` / `touch` / `render` は `destroyed` で停止 |
| 4 | Medium | `ResearchDocIn` の 422 形状検証が部分的 | `field` / `constraints` / `analysis`（field・配列・真偽値・quality 0〜5）/ `tasks`（10 件・key 集合・重複なし）/ `progress`・`runs`・`relevance`・`reliability`・`candidates.scores`・`weights`（有限・範囲）/ `candidate.label`（50 文字・文字列）・`id` / `plan` role を検証。クライアント sanitize も field・plan role の列挙、candidate label の型、analysis の形状を保証。422 回帰テストを 20 ケースに拡張 |
| 5 | Low | テーマ切替 E2E がサーバー永続化を拘束していない | 切替後に `page.reload()` して値を再確認 |
| 6 | Low | `flush` が同一プロジェクトを重複保存 | プロジェクト ID の集合でジョブを一意化 |
| 7 | Low | 次のステップ欄の二重エスケープ | 内側の `esc()` を外し、出力時の 1 回に統一（`A&B` が `A&amp;B` にならない） |
| 8 | Low | 仕様書の内部リンク切れ | `../adr/0004-auth-session.md` / `../architecture/01-architecture.md` に修正 |

## 3. 実測コマンド

```bash
.venv/bin/python -m pytest -p no:warnings        # 135 passed, 1 skipped
cd apps/web && npx vitest run                    # 10 passed
cd apps/web && npm run build && npx playwright test  # 21 passed (46.2s)
.venv/bin/ruff check apps/api tests
.venv/bin/ruff format --check apps/api tests
.venv/bin/python infra/db/export_openapi.py --check
```

注意: `pytest` と Playwright を**同時に実行しない**。同じ `rihrp_test*` DB を奪い合い、無関係なテストが落ちる（実際に `test_admin_cannot_demote_self` が偽陽性で落ちた）。単独実行では pass。

## 4. 未検証・残課題

- CI に E2E ジョブは未追加（workflow 変更は要人間承認）。
- スクリーンリーダー / キーボード全画面 / 320px / 実機 / ネットワーク遮断時の保存失敗 UI は未検証。
- レビュー3巡目の結果は本記録のコミット後に追記する。
