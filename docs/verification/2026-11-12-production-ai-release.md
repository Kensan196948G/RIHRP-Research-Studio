# 2026-11-12 本番: migration 0005 と AI 下書きの配備

- 実行: 2026-11-12 20:15〜20:45 JST
- 結果: 本番 `e3f59c6` / migration `0005_reports_ai_assisted` で稼働。ready 200・公開 302。
- 承認: 利用者選択 `1`（A〜F 実施）

## 1. 事前状態

| 項目 | 値 |
|---|---|
| 稼働リリース | `bfe717d`（0004） |
| previous | `4a96445`（0004） |
| 本番 DB | `rihrp_production` / 0004 |
| DB ロール | アプリ `rihrp_prod_app` / 所有者 `rihrp_prod_owner` |

## 2. 実施

| 段階 | 結果 |
|---|---|
| A. リリース機構の 0005 対応 | PR #34（`dc5449a`）。build/activate/preflight/runtime の期待 migration を 0005 に |
| A2. topology 修正 | PR #35（`8b557c1`）。旧 current/previous（0004）を許容 |
| B. バックアップ（0004） | `rihrp_production-20261112T111600723212-3037459.dump`（11表件数一致） |
| C. migration 0005 適用 | `rihrp_prod_app` は ALTER 不可のため OS 管理者で適用。列 `reports.ai_assisted`（boolean, not null, default false）を追加。所有者・既存行は不変（reports 0 行） |
| D. バックアップ（0005）＋復元 | `…-20261112T111702955135-3045880.dump`。専用 DB へ復元し 11 表件数一致、migration 0005。復元証跡を作成（0600） |
| E1. リリース build（初回） | `dc5449a`。隔離で health/ready・asset一致・実 AI（3候補・3.9秒）を確認 |
| E2. activate（初回） | **失敗**。新リリース venv に `httpx` が無く `ModuleNotFoundError`。旧 unit/pointer へ復旧したが旧リリースは 0005 DB で ready 503 のため「復旧失敗」扱い |
| 復旧 | PR #36（`e3f59c6`）で `httpx` を本番依存へ移動し requirements を再生成。中断マーカーは保存 unit/pointer と実体の一致を確認して解除 |
| E3. 再 build / 隔離受入 | `e3f59c6`。release venv の `httpx 0.28.1` を確認、隔離 ready 200 |
| E4. activate | **成功** 20:42:03。current=`e3f59c6` / previous=`bfe717d` |
| F. 配備後検証 | healthz 200 / readyz 200（0005）/ 公開 URL 302 / healthcheck OK |

## 3. 本番経路の AI 検証

本番 DB を書き換えないため、**最新バックアップを専用 DB へ復元**し、本番と同一リリース `e3f59c6`・本番 conf の鍵で実行した。

- ログイン → プロジェクト → 出典 → `ai/draft-claims`
- **200 / 4.4 秒 / 候補 2 件・有効 2 件**（`claude-opus-5-5`）
- 本番 DB への書込みなし（コピー DB は検証後に削除）

## 4. 障害記録（重要）

- **影響**: 20:17（migration 適用）〜20:42（切替完了）の約 25 分、`/readyz` が 503 `migration_pending`。
  `/healthz` は 200、公開 URL は 302 のまま。healthcheck が 5 回失敗を記録（20:21/20:26/20:31/20:37/20:42）。
- **原因1**: 本番 venv に `httpx` が無く、新リリースが起動できなかった（dev 依存にしか無かった）。
- **原因2**: 旧リリースは 0005 DB を想定しないため、migration 先行適用の間は ready になれない。
- **復旧**: 依存修正 → 再 build → 中断マーカー照合・解除 → activate。20:44 の healthcheck は OK。
- **残存**: 壊れたリリース `8b557c1` は releases に残置（current/previous からは参照されない）。

## 5. 切戻しの制約（新たに判明）

DB を 0005 に上げた後、**0004 リリース（`bfe717d`）へ戻すと readyz は 503 になる**（旧コードの期待 migration と DB が不一致）。
切戻しは次のいずれかが必要。

1. 0005 対応リリースへ切り替える（例: 直前の `e3f59c6` を再 activate）
2. DB を 0004 バックアップへ復元する（0005 以降のデータは失われる）

## 6. 未実施

- 所有者による本番ブラウザでの AI 下書き操作（Cloudflare Access のログインが必要）。
- 0004 への DB 復元を伴う切戻し訓練。
